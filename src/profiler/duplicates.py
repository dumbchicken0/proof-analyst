"""Duplicates detector for data quality profiling."""

from __future__ import annotations

from typing import List
import pandas as pd


def detect_duplicates_in_table(df: pd.DataFrame, table_name: str) -> List[str]:
    """Detect exact duplicate rows and near-duplicate primary IDs in a table."""
    messages: List[str] = []
    if df.empty:
        return messages

    # 1. Exact duplicate rows
    exact_row_dups = int(df.duplicated(keep="first").sum())

    # 2. Near-duplicate primary IDs (differing case / whitespace)
    # Target primary key column: e.g. order_id for orders, customer_id for customers, or 'id'
    tbl_singular = table_name[:-1].lower() if table_name.lower().endswith("s") else table_name.lower()
    expected_pk = f"{tbl_singular}_id"

    id_cols = []
    for c in df.columns:
        c_lower = c.lower()
        if c_lower == expected_pk or c_lower == "id":
            id_cols.append(c)

    # If no obvious singular match, check columns named *_id that have high uniqueness
    if not id_cols:
        for c in df.columns:
            if c.lower().endswith("_id"):
                unique_ratio = df[c].nunique() / max(len(df), 1)
                if unique_ratio > 0.8:
                    id_cols.append(c)

    near_dup_summary = []
    for id_col in id_cols:
        col_series = df[id_col].dropna().astype(str)
        s_norm = col_series.str.strip().str.lower()
        
        # Row-level masks
        raw_row_dup = df.duplicated(keep="first")
        norm_dup = s_norm.duplicated(keep="first")
        
        # Near duplicate is when normalized ID repeated, but row is not an exact row duplicate
        near_dup_mask = norm_dup & (~raw_row_dup)
        near_count = int(near_dup_mask.sum())
        if near_count > 0:
            near_dup_summary.append(f"{near_count} more repeat {id_col} with differing case/whitespace")

    if exact_row_dups > 0 or near_dup_summary:
        parts = []
        if exact_row_dups > 0:
            parts.append(f"{exact_row_dups} exact duplicate rows")
        if near_dup_summary:
            parts.extend(near_dup_summary)
        messages.append(f"[DUPLICATES] {table_name}: {'; '.join(parts)}")

    return messages


def detect_duplicates_in_column(df: pd.DataFrame, table_name: str, column_name: str) -> List[str]:
    """Detect duplicate issues specific to an identifier column."""
    messages: List[str] = []
    if column_name not in df.columns:
        return messages

    # Identifier check: only IDs are expected to be unique
    is_id = column_name.lower().endswith("_id") or column_name.lower() == "id"
    if not is_id:
        return messages

    # Check if this column is the primary key for the table
    tbl_singular = table_name[:-1].lower() if table_name.lower().endswith("s") else table_name.lower()
    is_pk = (column_name.lower() == f"{tbl_singular}_id") or (column_name.lower() == "id")

    s = df[column_name].dropna().astype(str)
    raw_dups = int(s.duplicated(keep="first").sum())
    s_norm = s.str.strip().str.lower()
    norm_dups = int(s_norm.duplicated(keep="first").sum())
    case_space_diff = norm_dups - raw_dups

    # If it is a foreign key, duplicate values are normal; only report case/whitespace issues
    if is_pk and raw_dups > 0:
        parts = [f"{raw_dups} duplicate values"]
        if case_space_diff > 0:
            parts.append(f"{case_space_diff} differing only by case/whitespace")
        messages.append(f"[DUPLICATES] {table_name}.{column_name}: {'; '.join(parts)}")
    elif not is_pk and case_space_diff > 0:
        messages.append(f"[DUPLICATES] {table_name}.{column_name}: {case_space_diff} values differing only by case/whitespace")

    return messages
