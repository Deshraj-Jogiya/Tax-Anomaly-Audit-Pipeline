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

## Does the ledger follow Benford's Law, and which test can be trusted at what size?

**How it was tested.** First digits of the amounts were tested against Benford's Law with a chi-square goodness-of-fit test (8
degrees of freedom) and the mean absolute deviation (MAD) read against Nigrini's first-digit ranges, on the whole ledger, each
department and the injected anomalies alone (`export_lab_data.py`).

| Amounts | Count | Chi-square | p-value | MAD | Nigrini's range |
|---|---|---|---|---|---|
| Whole ledger | 1,200 | 22.64 | 0.0039 | 0.0091 | acceptable conformity |
| Injected anomalies only | 47 | 346.38 | 5.4e-70 | 0.1792 | nonconformity |
| Engineering | 150 | 2.39 | 0.967 | 0.0101 | acceptable conformity |
| R&D | 197 | 4.73 | 0.786 | 0.0146 | marginal conformity |
| Sales | 174 | 16.70 | 0.0334 | 0.0261 | nonconformity |

**What it shows.** The 47 injected amounts are enough to pull the whole ledger off Benford (p = 0.0039) while its MAD still reads
"acceptable". At department size (150 to 200 amounts) the two tests disagree the other way: the four departments not shown above
(Finance, HR, Marketing, Operations) fit by chi-square (p from 0.07 to 0.38) yet fall in Nigrini's "nonconformity" range, which
was set for about 1,000 amounts.

**Decision.** Below about 1,000 amounts the chi-square p-value is the guide and MAD is shown for reference only (the portfolio Lab
demo says so on screen); the pipeline keeps per-entry Benford deviation as a 30% share of the risk score, not a flag of its own.

**Source.** `exports/lab_benford.json` (`fits`), `export_lab_data.py`.

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
