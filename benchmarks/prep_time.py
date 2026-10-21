"""Time the ledger validation step on a realistic volume: column operations (etl/validate.validate) against the same checks run
entry by entry (validate_rowwise). Builds a 100,000-entry ledger from the simulator's reference tables (seed 7), checks both
versions flag the same entries, and writes exports/prep_benchmark.csv."""

import os
import sys
import time

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from etl.audit_etl import ACCOUNTS, TAX_CATEGORIES, TAX_RATES  # noqa: E402
from etl.validate import validate, validate_rowwise  # noqa: E402


def synthetic_ledger(n=100_000, seed=7):
    rng = np.random.default_rng(seed)
    pairs = [(dept, acct) for dept, accts in ACCOUNTS.items() for acct in accts]
    pick = rng.integers(0, len(pairs), n)
    dept = np.array([pairs[i][0] for i in pick]); acct = np.array([pairs[i][1] for i in pick])
    category = np.array([TAX_CATEGORIES[a] for a in acct])
    amount = np.round(10 ** rng.uniform(1, 4, n), 2)
    tax = np.round(amount * np.array([TAX_RATES[c] for c in category]), 2)
    tax[rng.random(n) < 0.04] *= 3          # some claims off the statutory rate
    dates = (pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 365, n), unit="D")).strftime("%Y-%m-%d")
    return pd.DataFrame({"entry_id": np.arange(1, n + 1), "transaction_date": dates, "account_name": acct, "amount": amount,
                         "department": dept, "category": category, "tax_claimed": tax})


def timed(fn, df, repeats=3):
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter(); result = fn(df); best = min(best, time.perf_counter() - start)
    return result, best


if __name__ == "__main__":
    df = synthetic_ledger()
    fast, t_fast = timed(validate, df)
    slow, t_slow = timed(validate_rowwise, df, repeats=1)
    assert fast.equals(slow), "the two validators disagree"
    row = {"entries": len(df), "rowwise_seconds": round(t_slow, 3), "vectorised_seconds": round(t_fast, 3),
           "time_saved": round(1 - t_fast / t_slow, 4), "entries_flagged": int(fast.any(axis=1).sum())}
    os.makedirs(os.path.join(BASE, "exports"), exist_ok=True)
    pd.DataFrame([row]).to_csv(os.path.join(BASE, "exports", "prep_benchmark.csv"), index=False)
    print(row)
