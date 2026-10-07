"""Inject deterministic data quality traps into clean datasets.

MVP Traps injected:
1. Exact duplicates: 37 exact duplicate rows in orders.
2. Near-duplicates: 12 rows with altered casing/whitespace in order_id.
3. Mixed currencies: USD, EUR, INR present without prior conversion.
4. Mixed date formats:
   - 140 rows provably DD/MM/YYYY (day > 12)
   - 85 rows ambiguous DD/MM/YYYY (day <= 12 and month <= 12)
5. Missing values in orders.amount:
   - 24 NaN / None
   - 6 "N/A" strings
6. Orphan foreign keys:
   - 9 orders referencing customer_ids not present in customers table.
7. Category variations in customers.region:
   - "USA", "U.S.A.", "United States" variations for "North America".
8. Missing profit/cost column across the entire schema.
"""

from __future__ import annotations

import datetime as dt
import random
from typing import Any, Dict, Tuple
import numpy as np
import pandas as pd


def inject_traps(
    clean_dfs: Dict[str, pd.DataFrame],
    seed: int = 42,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any]]:
    """Inject traps into copies of the clean DataFrames deterministically."""
    rng = random.Random(seed)

    df_customers = clean_dfs["customers"].copy()
    df_orders = clean_dfs["orders"].copy()
    df_fx = clean_dfs["fx_rates"].copy()

    trap_stats: Dict[str, Any] = {}

    # ---------------------------------------------------------
    # 1. Customers category variations (USA / U.S.A. / United States)
    # ---------------------------------------------------------
    na_indices = df_customers[df_customers["region"] == "North America"].index.tolist()
    rng.shuffle(na_indices)
    spelling_variants = ["USA", "U.S.A.", "United States"]
    variant_count = min(len(na_indices), 15)
    for idx in na_indices[:variant_count]:
        df_customers.loc[idx, "region"] = rng.choice(spelling_variants)
    trap_stats["customer_region_variants"] = variant_count

    # ---------------------------------------------------------
    # Partition order indices to prevent interference between traps:
    # Set A: Date modifications
    # Set B: Missing amount modifications
    # Set C: Exact duplicates source
    # Set D: Near duplicates source
    # ---------------------------------------------------------
    
    # 2. Date format trap partition
    provably_dd_pool = []
    ambiguous_pool = []

    for idx, row in df_orders.iterrows():
        try:
            d = dt.date.fromisoformat(row["order_date"].strip())
            if d.day > 12:
                provably_dd_pool.append((idx, d))
            elif d.day <= 12 and d.month <= 12:
                ambiguous_pool.append((idx, d))
        except Exception:
            continue

    rng.shuffle(provably_dd_pool)
    rng.shuffle(ambiguous_pool)

    provable_count = 140
    ambiguous_count = 85

    provably_dd_chosen = provably_dd_pool[:provable_count]
    ambiguous_chosen = ambiguous_pool[:ambiguous_count]
    date_modified_indices = set([idx for idx, _ in provably_dd_chosen] + [idx for idx, _ in ambiguous_chosen])

    for idx, d in provably_dd_chosen:
        df_orders.loc[idx, "order_date"] = f"{d.day:02d}/{d.month:02d}/{d.year}"

    for idx, d in ambiguous_chosen:
        df_orders.loc[idx, "order_date"] = f"{d.day:02d}/{d.month:02d}/{d.year}"

    trap_stats["provably_dd_mm_dates"] = provable_count
    trap_stats["ambiguous_dates"] = ambiguous_count

    # 3. Missing amount trap partition
    # Plant on non-completed orders that were NOT modified for dates
    non_completed_pool = [
        idx for idx, row in df_orders.iterrows()
        if row["status"] in ["cancelled", "pending"] and idx not in date_modified_indices
    ]
    rng.shuffle(non_completed_pool)

    df_orders["amount"] = df_orders["amount"].astype("object")

    nan_indices = non_completed_pool[:24]
    for idx in nan_indices:
        df_orders.loc[idx, "amount"] = np.nan

    na_string_indices = non_completed_pool[24:30]
    for idx in na_string_indices:
        df_orders.loc[idx, "amount"] = "N/A"

    trap_stats["nan_amounts"] = len(nan_indices)
    trap_stats["na_string_amounts"] = len(na_string_indices)
    amount_modified_indices = set(nan_indices + na_string_indices)

    # 4. Duplicates partition: pick untouched rows
    untouched_indices = [
        idx for idx in df_orders.index
        if idx not in date_modified_indices and idx not in amount_modified_indices
    ]
    rng.shuffle(untouched_indices)

    # 37 exact duplicates
    exact_dup_indices = untouched_indices[:37]
    exact_dup_rows = df_orders.loc[exact_dup_indices].copy()

    # 12 near duplicates
    near_dup_indices = untouched_indices[37:49]
    near_dup_rows = df_orders.loc[near_dup_indices].copy()

    near_dup_records = near_dup_rows.to_dict("records")
    for i, record in enumerate(near_dup_records):
        original_oid = record["order_id"]
        if i % 2 == 0:
            record["order_id"] = original_oid.lower()
        else:
            record["order_id"] = f"  {original_oid}  "
    df_near_dups = pd.DataFrame(near_dup_records)

    trap_stats["exact_duplicate_rows"] = len(exact_dup_rows)
    trap_stats["near_duplicate_rows"] = len(df_near_dups)

    # 5. Orphan customer_ids: 9 orders
    orphan_rows = []
    for i in range(1, 10):
        orphan_cid = f"CUST-99{i:02d}"
        oid = f"ORD-99{i:02d}"
        orphan_rows.append({
            "order_id": oid,
            "customer_id": orphan_cid,
            "order_date": "2024-06-15",
            "amount": 100.0,
            "currency": "USD",
            "status": "completed",
        })
    df_orphans = pd.DataFrame(orphan_rows)
    trap_stats["orphan_customer_rows"] = len(df_orphans)

    # Concatenate all orders and shuffle deterministically
    raw_orders = pd.concat([df_orders, exact_dup_rows, df_near_dups, df_orphans], ignore_index=True)
    raw_orders = raw_orders.sample(frac=1.0, random_state=seed).reset_index(drop=True)

    raw_dfs = {
        "customers": df_customers,
        "fx_rates": df_fx,
        "orders": raw_orders,
    }

    return raw_dfs, trap_stats
