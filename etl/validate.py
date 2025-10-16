"""Validate general ledger entries and their tax claims before analysis.

Checks per entry: required fields present, a positive amount, a transaction date inside the ledger year, a known department and an
account that belongs to it, no duplicate entry ids, and a tax claim within one cent of the category's rate times the amount.
`validate` runs the checks as column operations; `validate_rowwise` is the same checks entry by entry, kept as the reference the
vectorised version is tested against and as the baseline for benchmarks/prep_time.py.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.audit_etl import ACCOUNTS, TAX_RATES  # noqa: E402

LEDGER_START, LEDGER_END = pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31")
REQUIRED = ["entry_id", "transaction_date", "account_name", "amount", "department", "category", "tax_claimed"]
CHECKS = ["missing_field", "non_positive_amount", "date_out_of_range", "unknown_account", "duplicate_entry", "tax_rate_mismatch"]
_ACCOUNT_DEPT = {acct: dept for dept, accts in ACCOUNTS.items() for acct in accts}


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """One boolean column per check (True = the entry fails it), in CHECKS order, indexed like df."""
    out = pd.DataFrame(index=df.index)
    out["missing_field"] = df[REQUIRED].isna().any(axis=1)
    amount = pd.to_numeric(df["amount"], errors="coerce")
    out["non_positive_amount"] = ~(amount > 0)
    dates = pd.to_datetime(df["transaction_date"], errors="coerce")
    out["date_out_of_range"] = ~dates.between(LEDGER_START, LEDGER_END)
    out["unknown_account"] = df["account_name"].map(_ACCOUNT_DEPT).ne(df["department"])
    out["duplicate_entry"] = df["entry_id"].duplicated(keep=False)
    expected = amount * df["category"].map(TAX_RATES)
    out["tax_rate_mismatch"] = ~((pd.to_numeric(df["tax_claimed"], errors="coerce") - expected).abs() <= 0.01 + 1e-9)
    return out[CHECKS]


def validate_rowwise(df: pd.DataFrame) -> pd.DataFrame:
    """The same checks, one entry at a time."""
    seen, dupes = set(), set()
    for entry_id in df["entry_id"]:
        (dupes if entry_id in seen else seen).add(entry_id)
    rows = []
    for _, r in df.iterrows():
        missing = any(pd.isna(r[c]) for c in REQUIRED)
        try:
            amount = float(r["amount"])
        except (TypeError, ValueError):
            amount = np.nan
        date = pd.to_datetime(r["transaction_date"], errors="coerce")
        rate = TAX_RATES.get(r["category"])
        try:
            claimed = float(r["tax_claimed"])
        except (TypeError, ValueError):
            claimed = np.nan
        rows.append({
            "missing_field": missing,
            "non_positive_amount": not amount > 0,
            "date_out_of_range": pd.isna(date) or not (LEDGER_START <= date <= LEDGER_END),
            "unknown_account": _ACCOUNT_DEPT.get(r["account_name"]) != r["department"],
            "duplicate_entry": r["entry_id"] in dupes,
            "tax_rate_mismatch": rate is None or not abs(claimed - amount * rate) <= 0.01 + 1e-9,
        })
    return pd.DataFrame(rows, index=df.index)[CHECKS]


def summary(flags: pd.DataFrame) -> dict:
    return {**{c: int(flags[c].sum()) for c in CHECKS}, "entries": len(flags), "entries_failing_any": int(flags.any(axis=1).sum())}

