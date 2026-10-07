"""Missing values and sentinel tokens detector for data quality profiling."""

from __future__ import annotations

from typing import List
import pandas as pd


SENTINEL_VALUES = ["N/A", "NA", "null", "NULL", "none", "None", "-", "missing", "nan"]


def detect_missing_in_table(df: pd.DataFrame, table_name: str) -> List[str]:
    """Detect missing values and sentinel strings across all columns in a table."""
    messages: List[str] = []
    if df.empty:
        return messages

    for col in df.columns:
        msgs = detect_missing_in_column(df, table_name, col)
        messages.extend(msgs)

    return messages


def detect_missing_in_column(df: pd.DataFrame, table_name: str, column_name: str) -> List[str]:
    """Detect missing values (NaN) and sentinel strings in a specific column."""
    messages: List[str] = []
    if column_name not in df.columns:
        return messages

    series = df[column_name]
    nan_count = int(series.isna().sum())

    # Check non-null values for sentinels and empty strings
    non_na = series.dropna().astype(str).str.strip()
    empty_count = int((non_na == "").sum())
    
    # If read with keep_default_na=False, empty strings represent missing/NaN
    effective_nan = nan_count if nan_count > 0 else empty_count

    sentinel_counts = {}
    for sentinel in SENTINEL_VALUES:
        cnt = int((non_na == sentinel).sum())
        if cnt > 0:
            sentinel_counts[sentinel] = cnt

    if effective_nan > 0 or sentinel_counts:
        parts = []
        if effective_nan > 0:
            parts.append(f"{effective_nan} NaN")
        for s_val, count in sentinel_counts.items():
            parts.append(f'{count} "{s_val}"')

        messages.append(f"[MISSING] {table_name}.{column_name}: {', '.join(parts)}")

    return messages
