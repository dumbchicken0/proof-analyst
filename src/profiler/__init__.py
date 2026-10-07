"""Data-quality profiler for proof-carrying data analyst agent."""

from __future__ import annotations

from typing import Any, Mapping
import pandas as pd


def profile_tables(dfs: Mapping[str, pd.DataFrame] | Any) -> str:
    """Produce a deterministic compact text summary of dataset-wide issues."""
    return ""


def profile_column(dfs: Mapping[str, pd.DataFrame] | Any, table: str, column: str) -> str:
    """Produce a deterministic compact text summary of issues for a specific column."""
    return ""
