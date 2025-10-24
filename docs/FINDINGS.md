# Findings

Measured results from this pipeline. The ledger is synthetic and seeded: the anomalies are injected by the generator and stored
apart from the tables the detectors read, so every result can be checked against the right answers.

## Which detection layer finds the injected anomalies: the model or the tax-rate rule?

**How it was tested.** Each layer was scored on its own against the injected anomalies. The model layer combines Benford's Law
first-digit deviation (30% of the risk score) with an Isolation Forest (70%) and flags entries at a risk score of 65. The rule layer
flags any claim whose tax doesn't match its category's rate.

| Layer | Flagged | True positives | Precision | Recall |
|---|---|---|---|---|
| Model (Benford + Isolation Forest) | 19 | 18 | 0.9474 | 0.383 |
| Tax-rate rule | 45 | 45 | 1.0 | 0.9574 |
| Combined | 46 | 45 | 0.9783 | 0.9574 |

**Decision.** The rule's flags go first in the review order, and the model and Benford's Law rank the rest. The rule alone finds
45 of the 47 injected anomalies with no false flags; every anomaly the model found, the rule had already found.

**Source.** `exports/detection_layers.csv`, `exports/detection_metrics.csv` (written by `models/audit_detection.py`).

## How much review work does the priority order save?

**How it was tested.** Entries were opened in priority order (rule hits, then risk score) and, separately, in ledger order,
counting how many must be opened to reach 90% of the injected anomalies.

| Metric | Priority order | Ledger order |
|---|---|---|
| Entries opened to find 90% of anomalies | 43 | 1,108 |
| Reduction in entries opened | 0.9612 | |

**Decision.** Review starts with the rule hits, then goes down the risk score (`review_effort` in `models/audit_detection.py`),
and the comparison is recomputed on every run.

**Source.** `exports/review_effort.csv`.

## Should validation run row by row or as column operations?

**How it was tested.** The same validation checks (required fields, positive amount, date in the ledger year, account belongs to
its department, no duplicates, tax equals the category rate times the amount) were run on 100,000 entries both ways. Both versions
flag the same entries.

| Metric | Row by row | Column operations |
|---|---|---|
| Time to validate | 40.579 s | 0.057 s |
| Entries flagged | 3405 | 3405 |
| Time saved | | 0.9986 |

**Decision.** `etl/validate.py` runs the checks as column operations.

**Source.** `exports/prep_benchmark.csv` (written by `benchmarks/prep_time.py`).
