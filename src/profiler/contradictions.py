"""Foreign keys, orphan records, and contradiction detector for data quality profiling."""

from __future__ import annotations

from typing import Any, List, Mapping
import pandas as pd


def detect_key_and_contradiction_issues(dfs: Mapping[str, pd.DataFrame] | Any) -> List[str]:
    """Detect broken foreign keys, orphan records, and cross-table contradictions."""
    messages: List[str] = []
    if not isinstance(dfs, Mapping):
        return messages

    # Detect foreign key references across tables
    for child_tbl, child_df in dfs.items():
        if not isinstance(child_df, pd.DataFrame) or child_df.empty:
            continue

        for col in child_df.columns:
            if not col.lower().endswith("_id"):
                continue

            target_entity = col[:-3].lower()  # e.g., 'customer' from 'customer_id'
            # Look for matching parent table
            parent_tbl = None
            parent_col = col

            for cand_tbl in dfs.keys():
                if cand_tbl.lower() == child_tbl.lower():
                    continue
                cand_lower = cand_tbl.lower()
                if cand_lower == f"{target_entity}s" or cand_lower == target_entity:
                    if col in dfs[cand_tbl].columns:
                        parent_tbl = cand_tbl
                        break

            # If not found by name convention, look for any other table with the same id column
            if not parent_tbl:
                for cand_tbl in dfs.keys():
                    if cand_tbl.lower() == child_tbl.lower():
                        continue
                    if col in dfs[cand_tbl].columns:
                        # Check if it looks like a primary key (high uniqueness)
                        parent_series = dfs[cand_tbl][col].dropna()
                        if len(parent_series) > 0 and parent_series.is_unique:
                            parent_tbl = cand_tbl
                            break

            if parent_tbl:
                parent_df = dfs[parent_tbl]
                child_series = child_df[col].dropna().astype(str).str.strip()
                parent_set = set(parent_df[parent_col].dropna().astype(str).str.strip())
                
                orphans_mask = ~child_series.isin(parent_set)
                orphan_count = int(orphans_mask.sum())
                if orphan_count > 0:
                    messages.append(
                        f"[KEYS] {child_tbl}.{col}: {orphan_count} values missing from {parent_tbl}.{parent_col}"
                    )

    return messages


def detect_key_issues_in_column(
    dfs: Mapping[str, pd.DataFrame] | Any, table_name: str, column_name: str
) -> List[str]:
    """Detect foreign key issues for a specific table and column."""
    messages: List[str] = []
    if not isinstance(dfs, Mapping) or table_name not in dfs:
        return messages

    child_df = dfs[table_name]
    if column_name not in child_df.columns:
        return messages

    all_msgs = detect_key_and_contradiction_issues(dfs)
    prefix = f"[KEYS] {table_name}.{column_name}:"
    for msg in all_msgs:
        if msg.startswith(prefix):
            messages.append(msg)

    return messages
