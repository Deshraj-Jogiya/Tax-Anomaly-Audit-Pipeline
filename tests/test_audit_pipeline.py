import os
import sqlite3
import subprocess
import sys

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from viz import powerbi_export as pe  # noqa: E402


def _run(script):
    subprocess.run([sys.executable, os.path.join(BASE, script)], check=True, cwd=BASE)


def setup_module(_):
    _run("etl/audit_etl.py")
    _run("models/audit_detection.py")


def test_labels_stay_out_of_the_detector_inputs():
    with sqlite3.connect(pe.DB_PATH) as conn:
        cols = {r[1] for t in ("general_ledger", "tax_claims") for r in conn.execute(f"PRAGMA table_info({t})")}
        injected = conn.execute("SELECT COUNT(*) FROM injected_anomalies").fetchone()[0]
    assert "injected_anomaly" not in cols and injected > 0


def test_metrics_match_a_hand_count():
    df = pd.DataFrame({"audit_flag": [1, 1, 1, 0, 0], "injected_anomaly": [1, 1, 0, 1, 0]})
    m = pe.detection_metrics(df.assign(entry_id=range(5))).iloc[0]
    assert m["true_positives"] == 2 and m["precision"] == round(2 / 3, 4) and m["recall"] == round(2 / 3, 4)


def test_export_shapes():
    with sqlite3.connect(pe.DB_PATH) as conn:
        df = pe.audited_entries(conn)
    assert len(df) == 1200 and df["risk_score"].notna().all()
    digits = pe.benford_digits(df)
    assert list(digits["first_digit"]) == list(range(1, 10))
    assert abs(digits["observed_share"].sum() - 1) < 0.01 and abs(digits["benford_share"].sum() - 1) < 0.01


def test_validator_checks_match_the_row_by_row_reference_and_catch_each_problem():
    from etl.validate import validate, validate_rowwise
    df = pd.DataFrame({
        "entry_id": [1, 2, 3, 3, 5, 6],
        "transaction_date": ["2025-03-01", "2025-03-01", "2024-12-31", "2025-05-01", "2025-06-01", None],
        "account_name": ["Audit Fees", "Audit Fees", "Audit Fees", "Lab Equipment", "Audit Fees", "Audit Fees"],
        "amount": [100.0, -5.0, 100.0, 200.0, 100.0, 100.0],
        "department": ["Finance", "Finance", "Finance", "Finance", "Finance", "Finance"],
        "category": ["VAT Exempt", "VAT Exempt", "VAT Exempt", "R&D Tax Credit", "VAT Exempt", "VAT Exempt"],
        "tax_claimed": [0.0, 0.0, 0.0, 50.0, 30.0, 0.0],
    })
    flags = validate(df)
    assert flags.equals(validate_rowwise(df))
    assert not flags.loc[0].any()                       # a clean entry
    assert flags.loc[1, "non_positive_amount"]
    assert flags.loc[2, "date_out_of_range"]
    assert flags.loc[3, "unknown_account"] and flags.loc[3, "duplicate_entry"]
    assert flags.loc[4, "tax_rate_mismatch"]            # 30 claimed on an exempt 100
    assert flags.loc[5, "missing_field"]


def test_review_effort_counts_entries_opened_in_each_order():
    from models.audit_detection import review_effort
    df = pd.DataFrame({"entry_id": range(1, 11), "rule_flag": [0] * 8 + [1, 1],
                       "compliance_risk_score": [1, 2, 3, 4, 5, 6, 7, 90, 10, 20]})
    truth = df["entry_id"].isin([8, 9, 10])
    e = review_effort(df, truth, share=1.0)
    assert e["entries_opened_priority_order"] == 3 and e["entries_opened_ledger_order"] == 10 and e["reduction"] == 0.7


def test_layer_metrics_are_written():
    layers = pd.read_csv(os.path.join(BASE, "exports", "detection_layers.csv"))
    assert list(layers["layer"]) == ["model", "rule", "combined"]
    assert layers.set_index("layer").loc["combined", "recall"] >= layers.set_index("layer").loc["model", "recall"]
