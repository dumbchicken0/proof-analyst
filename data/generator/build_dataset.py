"""CLI script to build clean dataset, compute ground-truth, inject traps, and write outputs.

Usage:
    python -m data.generator.build_dataset [--seed SEED]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

from data.generator.clean_data import generate_clean_dataset
from data.generator.traps import inject_traps


def compute_ground_truth_and_questions(
    clean_dfs: Dict[str, pd.DataFrame],
    trap_stats: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Compute ground-truth answers from clean data and generate the evaluation questions."""
    df_customers = clean_dfs["customers"]
    df_fx = clean_dfs["fx_rates"]
    df_orders = clean_dfs["orders"]

    # Calculate amount in USD for clean orders
    orders_merged = df_orders.merge(df_fx, on="currency", how="left")
    orders_merged["amount_usd"] = orders_merged["amount"] * orders_merged["rate_to_usd"]

    # q01: Total registered customers
    q01_val = float(len(df_customers))

    # q02: Rate to USD for EUR
    eur_rate = float(df_fx.loc[df_fx["currency"] == "EUR", "rate_to_usd"].iloc[0])

    # q03: Number of currencies in fx_rates
    q03_val = float(len(df_fx))

    # q04: Total revenue in USD for completed EUR orders
    eur_completed = orders_merged[
        (orders_merged["status"] == "completed") & (orders_merged["currency"] == "EUR")
    ]
    q04_val = round(float(eur_completed["amount_usd"].sum()), 2)

    # q05: Count of unique completed orders
    completed_orders = df_orders[df_orders["status"] == "completed"]
    q05_val = float(len(completed_orders))

    # q06: Total revenue in USD for completed orders by valid customers
    completed_merged = orders_merged[orders_merged["status"] == "completed"]
    valid_completed = completed_merged.merge(
        df_customers[["customer_id"]], on="customer_id", how="inner"
    )
    q06_val = round(float(valid_completed["amount_usd"].sum()), 2)

    # q07: Total revenue in USD for completed orders in Q1 2024 (2024-01-01 to 2024-03-31)
    q1_completed = valid_completed[
        (valid_completed["order_date"] >= "2024-01-01")
        & (valid_completed["order_date"] <= "2024-03-31")
    ]
    q07_val = round(float(q1_completed["amount_usd"].sum()), 2)

    # q08: Count of orders with missing or 'N/A' amount in raw data
    q08_val = float(trap_stats["nan_amounts"] + trap_stats["na_string_amounts"])

    questions: List[Dict[str, Any]] = [
        # --- 3 Clean Questions ---
        {
            "id": "q01",
            "question": "How many total registered customers are in the customers table?",
            "traps": [],
            "expected_verdict": "ANSWERED",
            "expected_value": q01_val,
            "tolerance": 0.0,
        },
        {
            "id": "q02",
            "question": "What is the conversion rate to USD for EUR in the fx_rates table?",
            "traps": [],
            "expected_verdict": "ANSWERED",
            "expected_value": eur_rate,
            "tolerance": 0.001,
        },
        {
            "id": "q03",
            "question": "How many distinct currency exchange rates are defined in fx_rates?",
            "traps": [],
            "expected_verdict": "ANSWERED",
            "expected_value": q03_val,
            "tolerance": 0.0,
        },
        # --- 5 Trap-Answerable Questions ---
        {
            "id": "q04",
            "question": "What is the total revenue in USD for all completed orders placed in EUR?",
            "traps": ["currency_conversion", "exact_duplicates", "near_duplicates"],
            "expected_verdict": "ANSWERED",
            "expected_value": q04_val,
            "tolerance": 0.5,
        },
        {
            "id": "q05",
            "question": "How many unique completed orders were placed in total?",
            "traps": ["exact_duplicates", "near_duplicates"],
            "expected_verdict": "ANSWERED",
            "expected_value": q05_val,
            "tolerance": 0.0,
        },
        {
            "id": "q06",
            "question": "What is the total revenue in USD for completed orders placed by valid registered customers?",
            "traps": ["orphan_foreign_keys", "currency_conversion", "exact_duplicates", "near_duplicates"],
            "expected_verdict": "ANSWERED",
            "expected_value": q06_val,
            "tolerance": 0.5,
        },
        {
            "id": "q07",
            "question": "What is the total revenue in USD for completed orders placed in the first quarter of 2024 (2024-01-01 to 2024-03-31 inclusive)?",
            "traps": ["mixed_date_formats", "currency_conversion", "exact_duplicates"],
            "expected_verdict": "ANSWERED",
            "expected_value": q07_val,
            "tolerance": 0.5,
        },
        {
            "id": "q08",
            "question": "What is the total number of orders in the orders table that have a missing, null, or 'N/A' amount?",
            "traps": ["missing_values"],
            "expected_verdict": "ANSWERED",
            "expected_value": q08_val,
            "tolerance": 0.0,
        },
        # --- 4 Unanswerable / Ambiguous / Refused Questions ---
        {
            "id": "q09",
            "question": "What was the total net profit in USD across all completed orders in 2024?",
            "traps": ["unanswerable_missing_profit_cost"],
            "expected_verdict": "REFUSED",
            "expected_value": None,
            "tolerance": None,
        },
        {
            "id": "q10",
            "question": "What was the total revenue in USD for orders placed between 2018-01-01 and 2018-12-31?",
            "traps": ["out_of_range_dates"],
            "expected_verdict": "REFUSED",
            "expected_value": None,
            "tolerance": None,
        },
        {
            "id": "q11",
            "question": "What is the average order amount in USD for orders shipped via 'hyperloop'?",
            "traps": ["false_premise_shipping_method"],
            "expected_verdict": "REFUSED",
            "expected_value": None,
            "tolerance": None,
        },
        {
            "id": "q12",
            "question": "What will be the projected total revenue in USD for the fourth quarter of 2027?",
            "traps": ["forecast_unanswerable"],
            "expected_verdict": "REFUSED",
            "expected_value": None,
            "tolerance": None,
        },
    ]

    return questions


def generate_data_dictionary_md() -> str:
    """Generate Markdown content for data/raw/data_dictionary.md.

    Leaves orders.amount unit undocumented on purpose.
    """
    return """# Retail Dataset Data Dictionary

This document details tables, columns, data types, and units for the raw retail dataset.

## Tables Overview

1. `customers`: Registered customer accounts.
2. `orders`: Order transactions placed across multiple global regions.
3. `fx_rates`: Foreign exchange conversion rates relative to USD.

---

## 1. Table: `customers`

| Column Name | Data Type | Description | Units / Format |
| :--- | :--- | :--- | :--- |
| `customer_id` | String | Unique customer identifier | Format: `CUST-XXXX` |
| `name` | String | Full name of the customer | Text |
| `region` | String | Geographical market area (e.g., North America, Europe, Asia-Pacific, Latin America) | Categorical text |
| `signup_date`| String | Customer registration date | ISO format `YYYY-MM-DD` |

---

## 2. Table: `fx_rates`

| Column Name | Data Type | Description | Units / Format |
| :--- | :--- | :--- | :--- |
| `currency` | String | Three-letter currency code | ISO 4217 code (e.g. `USD`, `EUR`, `INR`, `GBP`) |
| `rate_to_usd` | Float | Multiplier to convert local currency amount into USD equivalent | USD per 1 unit of foreign currency |

*Example Conversion*: `amount_usd = amount * rate_to_usd`

---

## 3. Table: `orders`

| Column Name | Data Type | Description | Units / Format |
| :--- | :--- | :--- | :--- |
| `order_id` | String | Unique transaction identifier | Format: `ORD-XXXX` (may contain data entry variations) |
| `customer_id` | String | Customer who initiated the purchase | Foreign key referencing `customers.customer_id` |
| `order_date` | String | Date of order placement | Date string (contains mixed international formats) |
| `amount` | Numeric / String | Transaction magnitude recorded at purchase | *[Undocumented]* |
| `currency` | String | Currency code associated with the order | ISO 4217 code (e.g. `USD`, `EUR`, `INR`) |
| `status` | String | Fulfillment status (`completed`, `pending`, `cancelled`, `returned`) | Categorical text |

> **Note on `orders.amount`**: The unit of measurement for `amount` is left undocumented in legacy records; analysts should verify whether values represent raw local currency or converted values using `currency` and `fx_rates`.
"""


def build(seed: int = 42, base_dir: Path | None = None) -> None:
    """Run full build process."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent.parent

    raw_dir = base_dir / "data" / "raw"
    eval_dir = base_dir / "data" / "eval"
    raw_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Generating clean dataset (seed={seed})...")
    clean_dfs = generate_clean_dataset(seed=seed)

    print("[*] Injecting traps...")
    raw_dfs, trap_stats = inject_traps(clean_dfs, seed=seed)

    print("[*] Computing ground-truth and generating 12 evaluation questions...")
    questions = compute_ground_truth_and_questions(clean_dfs, trap_stats)

    # 1. Write raw CSV files
    print(f"[*] Writing raw CSVs to {raw_dir}...")
    for table_name, df in raw_dfs.items():
        csv_path = raw_dir / f"{table_name}.csv"
        df.to_csv(csv_path, index=False)
        print(f"    - Wrote {table_name}.csv ({len(df)} rows)")

    # 2. Write data_dictionary.md
    dict_path = raw_dir / "data_dictionary.md"
    dict_path.write_text(generate_data_dictionary_md(), encoding="utf-8")
    print(f"    - Wrote {dict_path.name}")

    # 3. Write questions.jsonl
    q_path = eval_dir / "questions.jsonl"
    with open(q_path, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q) + "\n")
    print(f"    - Wrote {q_path.name} ({len(questions)} questions)")

    # Print summary
    print("\n================== BUILD SUMMARY ==================")
    print(f"Seed: {seed}")
    print("Trap Statistics:")
    for k, v in trap_stats.items():
        print(f"  - {k}: {v}")
    print("\nQuestions Generated:")
    for q in questions:
        print(f"  [{q['id']}] {q['expected_verdict']}: {q['question'][:65]}... (val={q['expected_value']})")
    print("===================================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dataset and evaluation questions.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()
    build(seed=args.seed)


if __name__ == "__main__":
    main()
