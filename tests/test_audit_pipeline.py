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
