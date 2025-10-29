"""Exports the audited ledger for the portfolio Lab demo, with Python's results for every number the demo recomputes.

Usage: python export_lab_data.py <output.json>

The demo draws the ledger's first-digit distribution against Benford's Law, tests the fit, and lets a visitor reweight the risk
score. It recomputes the Benford parts in the browser and reads the Isolation Forest scores and the tax-rate rule flags as data
(they come from models/audit_detection.py and are not recomputed). This writes:
- entries: amount, department, category, Isolation Forest score, rule flag, whether the generator injected an anomaly, and the
  Benford and combined risk scores Python gave each entry;
- fits: Benford goodness-of-fit (chi-square with SciPy, and the mean absolute deviation) on the whole ledger, each department and
  the injected entries alone, so the browser's statistics can be checked on several inputs;
- layers: Python's detection-layer results at the project's own settings (30% Benford, 70% Isolation Forest, flag at 65).
"""
import json
import os
import sqlite3
import sys

import numpy as np
from scipy.stats import chisquare

from models.audit_detection import calculate_benford_scores, compute_compliance_scores, load_data, run_isolation_forest

BENFORD = np.log10(1 + 1 / np.arange(1, 10))
# Nigrini's first-digit conformity ranges for the mean absolute deviation
MAD_RANGES = [(0.006, "close conformity"), (0.012, "acceptable conformity"), (0.015, "marginal conformity"), (np.inf, "nonconformity")]


def benford_fit(first_digits) -> dict:
    digits = np.asarray([d for d in first_digits if 1 <= d <= 9])
    counts = np.array([(digits == d).sum() for d in range(1, 10)])
    stat, p = chisquare(counts, BENFORD * len(digits))
    mad = float(np.abs(counts / len(digits) - BENFORD).mean())
    return {"n": int(len(digits)), "counts": counts.tolist(), "chi_square": round(float(stat), 8), "p": float(p),
            "mad": round(mad, 8), "conformity": next(label for limit, label in MAD_RANGES if mad <= limit)}


def main(out_path: str) -> None:
    db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tax_compliance.db")
    df = run_isolation_forest(calculate_benford_scores(load_data(db)))
    compute_compliance_scores(df, db)
    conn = sqlite3.connect(db)
    injected = {r[0] for r in conn.execute("SELECT entry_id FROM injected_anomalies")}
    conn.close()
    df["injected"] = df.entry_id.isin(injected).astype(int)

    entries = [{"id": int(r.entry_id), "department": r.department, "category": r.category, "amount": float(r.amount),
                "iforest": round(float(r.iforest_score), 8), "rule": int(r.rule_flag), "injected": int(r.injected),
                "benford_score": round(float(r.benford_dev_score), 8), "risk": round(float(r.compliance_risk_score), 6)}
               for r in df.itertuples()]
    fits = {"All entries": benford_fit(df.first_digit), "Injected anomalies only": benford_fit(df[df.injected == 1].first_digit)}
    for dept in sorted(df.department.unique()):
        fits[dept] = benford_fit(df[df.department == dept].first_digit)
    truth = df.injected == 1
    layers = {}
    for name, col in (("model", "model_flag"), ("rule", "rule_flag"), ("combined", "audit_flag")):
        flagged = df[col] == 1
        layers[name] = {"flagged": int(flagged.sum()), "true_positives": int((flagged & truth).sum())}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"note": "Synthetic, seeded ledger (etl/audit_etl.py); anomalies injected by the generator.",
                   "weights": {"benford": 0.3, "iforest": 0.7}, "threshold": 65.0, "mad_ranges": [[l if np.isfinite(l) else None, s] for l, s in MAD_RANGES],
                   "entries": entries, "fits": fits, "layers": layers}, f, separators=(",", ":"))
    print(f"{len(entries)} entries, {len(fits)} Benford fits and the layer results written to {out_path}")


if __name__ == "__main__":
    main(sys.argv[1])
