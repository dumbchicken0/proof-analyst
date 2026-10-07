"""Date formats and ambiguity detector for data quality profiling."""

from __future__ import annotations

import re
from typing import List
import pandas as pd


DATE_SLASH_REGEX = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
DATE_ISO_REGEX = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


def detect_date_issues_in_table(df: pd.DataFrame, table_name: str) -> List[str]:
    """Detect mixed date formats and ambiguous date values across a table."""
    messages: List[str] = []
    if df.empty:
        return messages

    for col in df.columns:
        col_lower = col.lower()
        if "date" in col_lower or "time" in col_lower:
            msgs = detect_date_issues_in_column(df, table_name, col)
            messages.extend(msgs)

    return messages


def detect_date_issues_in_column(df: pd.DataFrame, table_name: str, column_name: str) -> List[str]:
    """Detect date format issues in a specific column."""
    messages: List[str] = []
    if column_name not in df.columns:
        return messages

    values = df[column_name].dropna().astype(str).str.strip().tolist()
    if not values:
        return messages

    iso_count = 0
    provably_dd_count = 0
    provably_mm_count = 0
    ambiguous_count = 0
    other_count = 0

    for v in values:
        m_iso = DATE_ISO_REGEX.match(v)
        if m_iso:
            iso_count += 1
            continue

        m_slash = DATE_SLASH_REGEX.match(v)
        if m_slash:
            p1 = int(m_slash.group(1))
            p2 = int(m_slash.group(2))
            if p1 > 12:
                provably_dd_count += 1
            elif p2 > 12:
                provably_mm_count += 1
            else:
                ambiguous_count += 1
            continue

        other_count += 1

    total_slash = provably_dd_count + provably_mm_count + ambiguous_count
    # Check if mixed formats are present
    if (iso_count > 0 and total_slash > 0) or (provably_dd_count > 0 and ambiguous_count > 0):
        details = []
        if provably_dd_count > 0:
            details.append(f"{provably_dd_count} rows provably DD/MM (day>12)")
        if provably_mm_count > 0:
            details.append(f"{provably_mm_count} rows provably MM/DD (day>12)")
        if ambiguous_count > 0:
            details.append(f"{ambiguous_count} ambiguous")

        msg = f"[DATES] {table_name}.{column_name}: mixed formats; {', '.join(details)}"
        messages.append(msg)

    return messages
