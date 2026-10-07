# LightC Engineering Notes: Test Data, Profiler & Evaluation Harness

This document records the design decisions, schemas, planted traps, question benchmarks, and profiler implementation for teammate `lightC`.

---

## 1. Responsibilities & Ownership

- **Data Generator**: `data/generator/` (`clean_data.py`, `traps.py`, `build_dataset.py`)
- **Raw Artifacts**: `data/raw/` (`customers.csv`, `orders.csv`, `fx_rates.csv`, `data_dictionary.md`)
- **Evaluation Benchmark**: `data/eval/` (`questions.jsonl`), `eval/run_eval.py`
- **Data Profiler**: `src/profiler/` (`duplicates.py`, `currency.py`, `dates.py`, `missing.py`, `contradictions.py`)
- **Tests**: `tests/` (`test_generator.py`, `test_profiler.py`, `test_eval_harness.py`)
- **Notes**: `docs/NOTES_lightC.md`

---

## 2. Dataset Generation Strategy

### The Ground-Truth Trick
1. **Clean Baseline First**: Generated clean baseline DataFrames for:
   - `customers` (200 rows): clean IDs (`CUST-0001`..`CUST-0200`), regions, ISO signup dates (`YYYY-MM-DD`).
   - `fx_rates` (4 rows): USD (1.0), EUR (1.08), INR (0.012), GBP (1.25).
   - `orders` (1,000 clean rows): clean IDs (`ORD-0001`..`ORD-1000`), valid customer foreign keys, ISO dates (`YYYY-MM-DD`), numeric positive amounts, clean currencies (`USD`, `EUR`, `INR`), statuses (`completed`, `pending`, `cancelled`, `returned`).
2. **Compute Ground-Truth Answers**: Computed exact answers with pandas directly from clean DataFrames before any distortion was applied.
3. **Planted Traps**: Injected realistic data traps on disjoint subsets in `data/generator/traps.py` so ground-truth values remain strictly recoverable by a clean agent that properly remediates data defects.

### Trap Counts Planted (Seed 42)
| Trap Description | Count | Location | Remediation Required |
| :--- | :--- | :--- | :--- |
| **Exact Duplicates** | 37 rows | `orders` | Exact row deduplication |
| **Near-Duplicates** | 12 rows | `orders.order_id` | Whitespace stripping and case-insensitive deduplication |
| **Mixed Currencies** | 3 currencies | `orders.amount`, `orders.currency` | Join `fx_rates` and multiply by `rate_to_usd` |
| **Provably DD/MM Dates** | 140 rows | `orders.order_date` | Parse slash dates with `day > 12` as DD/MM/YYYY |
| **Ambiguous Dates** | 85 rows | `orders.order_date` | Identify ambiguity when both day and month <= 12 |
| **Missing Amount NaNs** | 24 rows | `orders.amount` | Filter or handle null amounts (placed on non-completed orders) |
| **Sentinel String Amounts** | 6 rows | `orders.amount` | Coerce sentinel `"N/A"` to null/numeric |
| **Orphan Foreign Keys** | 9 rows | `orders.customer_id` | Inner join with `customers` to eliminate unlinked orders (`CUST-9901`..`CUST-9909`) |
| **Category Spellings** | 15 rows | `customers.region` | Normalize "USA", "U.S.A.", "United States" |
| **Unanswerable Topic** | Full schema | Missing cost/profit | Must refuse or flag unanswerable |

### Data Dictionary & Undocumented Unit
- Written to `data/raw/data_dictionary.md`.
- As required by the contract, the measurement unit for `orders.amount` is intentionally left undocumented (`[Undocumented]`).

---

## 3. Evaluation Questions Benchmark (`data/eval/questions.jsonl`)

The benchmark consists of 12 questions across 3 tiers:

### Clean Questions (3)
- `q01`: Total registered customers in `customers` table -> `200.0` (tolerance: `0.0`)
- `q02`: Conversion rate to USD for EUR in `fx_rates` -> `1.08` (tolerance: `0.001`)
- `q03`: Distinct currency exchange rates in `fx_rates` -> `4.0` (tolerance: `0.0`)

### Trap-Answerable Questions (5)
- `q04`: Total revenue in USD for all completed EUR orders -> `90429.52` (tolerance: `0.5`, traps: `currency_conversion`, `exact_duplicates`, `near_duplicates`)
- `q05`: Unique completed orders count -> `704.0` (tolerance: `0.0`, traps: `exact_duplicates`, `near_duplicates`)
- `q06`: Total revenue in USD for completed orders by valid customers -> `291431.29` (tolerance: `0.5`, traps: `orphan_foreign_keys`, `currency_conversion`, `exact_duplicates`, `near_duplicates`)
- `q07`: Total revenue in USD for completed orders placed in Q1 2024 -> `69161.24` (tolerance: `0.5`, traps: `mixed_date_formats`, `currency_conversion`, `exact_duplicates`)
- `q08`: Count of orders with missing or 'N/A' amount in raw data -> `30.0` (tolerance: `0.0`, traps: `missing_values`)

### Unanswerable / Refused / Ambiguous Questions (4)
- `q09`: Net profit in USD in 2024 (missing cost/profit column) -> `expected_verdict`: `REFUSED`, `expected_value`: `null`
- `q10`: Revenue for date range 2018 (out of dataset bounds) -> `expected_verdict`: `REFUSED`, `expected_value`: `null`
- `q11`: Orders shipped via 'hyperloop' (false premise) -> `expected_verdict`: `REFUSED`, `expected_value`: `null`
- `q12`: Forecasted revenue for Q4 2027 (unsupported future prediction) -> `expected_verdict`: `REFUSED`, `expected_value`: `null`

---

## 4. Profiler Engine (`src/profiler/`)

### Design & Behavior
- **Zero LLM**: Fully deterministic, rule-based, and fast (< 50ms).
- **Interface**:
  - `profile_tables(dfs: Mapping[str, pd.DataFrame]) -> str`
  - `profile_column(dfs: Mapping[str, pd.DataFrame], table: str, column: str) -> str`
- **Output Sample on Raw Data**:
```text
[DUPLICATES] orders: 37 exact duplicate rows; 12 more repeat order_id with differing case/whitespace
[CURRENCY] orders.amount has currency column values {EUR, INR, USD}; amounts are not comparable
[DATES] orders.order_date: mixed formats; 140 rows provably DD/MM (day>12), 85 ambiguous
[MISSING] orders.amount: 24 NaN, 6 "N/A"
[KEYS] orders.customer_id: 9 values missing from customers.customer_id
```

---

## 5. Evaluation Harness (`eval/run_eval.py`)

### Features
- Reads `questions.jsonl` and invokes `src.agent.run_agent(question, dfs)`.
- Supports `--stub` flag for zero-dependency execution.
- Supports `--limit N` and `--ids q01,q02` filtering.
- Metrics reported:
  - **Accuracy**: Overall fraction of questions matching expected verdict and numeric value within tolerance.
  - **Re-run Success Rate**: Fraction of answered questions where `answer.proof.reproduced == True`.
  - **Correct Refusal Rate**: Fraction of refused/ambiguous questions correctly identified.
  - **Confident-Wrong Rate**: Fraction of questions where agent produced an erroneous numeric answer or answered an unanswerable question.
- Outputs console report and writes persistent JSON benchmark to `eval/results.json`.

---

## 6. Verification & Test Suite

All 12 unit tests pass in pytest:
- `tests/test_generator.py`: Verifies seeded determinism, trap counts, data dictionary, and question schemas.
- `tests/test_profiler.py`: Tests each detector on isolated tiny hand-made DataFrames.
- `tests/test_eval_harness.py`: Tests response extraction, scoring rules (passes, errors, confident-wrong), and end-to-end evaluation.
