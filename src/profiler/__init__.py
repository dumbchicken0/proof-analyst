"""Data-quality profiler for proof-carrying data analyst agent.

Fully deterministic, fast, rule-based profiler without LLM dependencies.
"""

from __future__ import annotations

from typing import Any, List, Mapping
import pandas as pd

from src.profiler.contradictions import (
    detect_key_and_contradiction_issues,
    detect_key_issues_in_column,
)
from src.profiler.currency import (
    detect_currency_issues_in_column,
    detect_currency_issues_in_table,
)
from src.profiler.dates import (
    detect_date_issues_in_column,
    detect_date_issues_in_table,
)
from src.profiler.duplicates import (
    detect_duplicates_in_column,
    detect_duplicates_in_table,
)
from src.profiler.missing import (
    detect_missing_in_column,
    detect_missing_in_table,
)


def profile_tables(dfs: Mapping[str, pd.DataFrame] | Any) -> str:
    """Produce a deterministic compact text summary of dataset-wide data quality issues."""
    if not isinstance(dfs, Mapping) or not dfs:
        return ""

    lines: List[str] = []

    # 1. Duplicates across all tables
    for table_name, df in dfs.items():
        if isinstance(df, pd.DataFrame):
            lines.extend(detect_duplicates_in_table(df, table_name))

    # 2. Currency issues across all tables
    for table_name, df in dfs.items():
        if isinstance(df, pd.DataFrame):
            lines.extend(detect_currency_issues_in_table(df, table_name))

    # 3. Date format and ambiguity issues across all tables
    for table_name, df in dfs.items():
        if isinstance(df, pd.DataFrame):
            lines.extend(detect_date_issues_in_table(df, table_name))

    # 4. Missing values and sentinels across all tables
    for table_name, df in dfs.items():
        if isinstance(df, pd.DataFrame):
            lines.extend(detect_missing_in_table(df, table_name))

    # 5. Cross-table foreign key & contradiction issues
    lines.extend(detect_key_and_contradiction_issues(dfs))

    return "\n".join(lines)


def profile_column(dfs: Mapping[str, pd.DataFrame] | Any, table: str, column: str) -> str:
    """Produce a deterministic compact text summary of issues for a specific column."""
    if not isinstance(dfs, Mapping) or table not in dfs:
        return ""

    df = dfs[table]
    if not isinstance(df, pd.DataFrame) or column not in df.columns:
        return ""

    lines: List[str] = []

    # Column-level duplicates
    lines.extend(detect_duplicates_in_column(df, table, column))

    # Column-level currency
    lines.extend(detect_currency_issues_in_column(df, table, column))

    # Column-level dates
    lines.extend(detect_date_issues_in_column(df, table, column))

    # Column-level missing
    lines.extend(detect_missing_in_column(df, table, column))

    # Column-level key references
    lines.extend(detect_key_issues_in_column(dfs, table, column))

    return "\n".join(lines)


__all__ = [
    "profile_tables",
    "profile_column",
]
