"""Dagster orchestration for the real ETL -> audit -> dashboard pipeline
(etl/audit_etl.py -> models/audit_detection.py -> viz/dashboard_export.py),
wrapped as three dependent assets instead of three manually-run scripts.

Run it for real:
    dagster asset materialize -f dagster_pipeline.py --select "*"
"""

import os

from dagster import AssetExecutionContext, Definitions, asset

from etl.audit_etl import create_db_and_schema, simulate_data
from models.audit_detection import (
    calculate_benford_scores,
    compute_compliance_scores,
    load_data,
    run_isolation_forest,
)
from viz.dashboard_export import export_dashboard, load_audited_data

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "tax_compliance.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "db", "schema.sql")
DASHBOARD_PATH = os.path.join(BASE_DIR, "viz", "tableau_ai_observability.png")


@asset
def raw_ledger_data(context: AssetExecutionContext) -> str:
    """Simulates and loads general ledger + tax claim entries into SQLite."""
    create_db_and_schema(DB_PATH, SCHEMA_PATH)
    simulate_data(DB_PATH, num_entries=1200)
    context.log.info(f"Loaded raw ledger data into {DB_PATH}")
    return DB_PATH


@asset
def audited_ledger_data(context: AssetExecutionContext, raw_ledger_data: str) -> str:
    """Runs Benford's Law scoring and Isolation Forest anomaly detection
    against the raw ledger data, writing compliance risk scores back to
    the database."""
    df = load_data(raw_ledger_data)
    df = calculate_benford_scores(df)
    df = run_isolation_forest(df)
    compute_compliance_scores(df, raw_ledger_data)
    context.log.info(f"Audited {len(df):,} ledger entries")
    return raw_ledger_data


@asset
def compliance_dashboard(context: AssetExecutionContext, audited_ledger_data: str) -> str:
    """Exports the compliance dashboard PNG from the audited data."""
    df = load_audited_data(audited_ledger_data)
    export_dashboard(df, DASHBOARD_PATH)
    context.log.info(f"Dashboard exported to {DASHBOARD_PATH}")
    return DASHBOARD_PATH


defs = Definitions(assets=[raw_ledger_data, audited_ledger_data, compliance_dashboard])
