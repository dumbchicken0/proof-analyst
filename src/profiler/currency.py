"""Currency issues detector for data quality profiling."""

from __future__ import annotations

import re
from typing import List
import pandas as pd


MONETARY_COL_KEYWORDS = ["amount", "price", "total", "cost", "revenue", "subtotal", "fee", "tax"]
CURRENCY_COL_KEYWORDS = ["currency", "curr", "curr_code"]


def detect_currency_issues_in_table(df: pd.DataFrame, table_name: str) -> List[str]:
    """Detect currency mismatch or non-comparable amounts across a table."""
    messages: List[str] = []
    if df.empty:
        return messages

    cols_lower = {c.lower(): c for c in df.columns}
    
    # Identify currency columns
    curr_col_name = None
    for kw in CURRENCY_COL_KEYWORDS:
        if kw in cols_lower:
            curr_col_name = cols_lower[kw]
            break

    # Identify monetary columns
    monetary_cols = [cols_lower[kw] for kw in MONETARY_COL_KEYWORDS if kw in cols_lower]

    if curr_col_name and monetary_cols:
        raw_vals = df[curr_col_name].dropna().astype(str).str.strip().unique().tolist()
        unique_currencies = sorted([v for v in raw_vals if v and v.upper() != "NAN"])
        
        if len(unique_currencies) > 1:
            # Format display matching example: {USD, EUR, INR}
            curr_str = "{" + ", ".join(unique_currencies) + "}"
            for mcol in monetary_cols:
                messages.append(
                    f"[CURRENCY] {table_name}.{mcol} has currency column values {curr_str}; amounts are not comparable"
                )

    # Check for embedded currency symbols in text
    for col in df.columns:
        if col == curr_col_name:
            continue
        sample_str = df[col].dropna().astype(str)
        has_symbols = sample_str.str.contains(r"[\$€₹£¥]", regex=True).any()
        if has_symbols and col in monetary_cols:
            messages.append(
                f"[CURRENCY] {table_name}.{col} contains embedded currency symbols; values require normalization"
            )

    return messages


def detect_currency_issues_in_column(df: pd.DataFrame, table_name: str, column_name: str) -> List[str]:
    """Detect currency issues for a specific column."""
    messages: List[str] = []
    if column_name not in df.columns:
        return messages

    # If this column is a monetary column, check if there is an associated currency column
    col_lower = column_name.lower()
    cols_lower = {c.lower(): c for c in df.columns}
    curr_col_name = None
    for kw in CURRENCY_COL_KEYWORDS:
        if kw in cols_lower:
            curr_col_name = cols_lower[kw]
            break

    if any(kw in col_lower for kw in MONETARY_COL_KEYWORDS) and curr_col_name:
        raw_vals = df[curr_col_name].dropna().astype(str).str.strip().unique().tolist()
        unique_currencies = sorted([v for v in raw_vals if v and v.upper() != "NAN"])
        if len(unique_currencies) > 1:
            curr_str = "{" + ", ".join(unique_currencies) + "}"
            messages.append(
                f"[CURRENCY] {table_name}.{column_name} has currency column values {curr_str}; amounts are not comparable"
            )

    return messages
