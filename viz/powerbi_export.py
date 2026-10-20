"""Export the audited ledger as flat CSV files for the Power BI report (powerbi/tax_audit_dashboard.pbix).

Writes to exports/:
- audited_entries.csv: one row per ledger entry with its scores, audit flag and whether the simulator injected it as an anomaly
- benford_digits.csv: observed vs expected first-digit share (Benford's Law)
- department_summary.csv: entries, flagged entries, average risk score and amount per department
- detection_metrics.csv: precision and recall of the audit flags against the injected anomalies
"""

import os
import sqlite3
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
DB_PATH = os.path.join(BASE, "data", "tax_compliance.db")
OUT_DIR = os.path.join(BASE, "exports")


def audited_entries(conn):
    df = pd.read_sql_query(
        """
        SELECT gl.entry_id, gl.transaction_date, gl.department, gl.account_name, tc.category, gl.amount,
               tc.tax_claimed, ROUND(tc.audit_score, 2) AS risk_score, tc.audit_flag,
               CASE WHEN ia.entry_id IS NULL THEN 0 ELSE 1 END AS injected_anomaly
        FROM general_ledger gl
        JOIN tax_claims tc ON gl.entry_id = tc.entry_id
        LEFT JOIN injected_anomalies ia ON gl.entry_id = ia.entry_id
        """,
        conn,
    )
    df["tax_ratio"] = (df["tax_claimed"] / df["amount"].where(df["amount"] != 0)).round(4)
    return df


def first_digit(amount):
    s = f"{abs(amount):.10f}".replace(".", "").lstrip("0")
    return int(s[0]) if s else 0


def benford_digits(df):
    digits = df["amount"].map(first_digit)
    digits = digits[digits.between(1, 9)]
    observed = digits.value_counts(normalize=True).reindex(range(1, 10), fill_value=0)
    return pd.DataFrame({
        "first_digit": range(1, 10),
        "observed_share": observed.round(4).values,
        "benford_share": [round(float(np.log10(1 + 1 / d)), 4) for d in range(1, 10)],
    })


def department_summary(df):
    return (df.groupby("department")
              .agg(entries=("entry_id", "size"), flagged=("audit_flag", "sum"),
                   avg_risk_score=("risk_score", "mean"), total_amount=("amount", "sum"))
              .round(2).reset_index())


def detection_metrics(df):
    flagged, truth = df["audit_flag"] == 1, df["injected_anomaly"] == 1
    tp = int((flagged & truth).sum())
    return pd.DataFrame([{
        "entries": len(df), "injected_anomalies": int(truth.sum()), "flagged": int(flagged.sum()), "true_positives": tp,
        "precision": round(tp / flagged.sum(), 4) if flagged.any() else 0.0,
        "recall": round(tp / truth.sum(), 4) if truth.any() else 0.0,
    }])


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        df = audited_entries(conn)
    if df["risk_score"].isna().all():
        raise SystemExit("No audit scores yet: run models/audit_detection.py first.")
    df.to_csv(os.path.join(OUT_DIR, "audited_entries.csv"), index=False)
    benford_digits(df).to_csv(os.path.join(OUT_DIR, "benford_digits.csv"), index=False)
    department_summary(df).to_csv(os.path.join(OUT_DIR, "department_summary.csv"), index=False)
    detection_metrics(df).to_csv(os.path.join(OUT_DIR, "detection_metrics.csv"), index=False)
    print(f"Wrote {len(df)} audited entries and summaries to {OUT_DIR}")


if __name__ == "__main__":
    main()
