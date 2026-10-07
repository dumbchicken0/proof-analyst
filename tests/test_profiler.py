"""Unit tests for data-quality profiler on tiny hand-made DataFrames."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.profiler import profile_column, profile_tables
from src.profiler.contradictions import detect_key_and_contradiction_issues
from src.profiler.currency import detect_currency_issues_in_table
from src.profiler.dates import detect_date_issues_in_table
from src.profiler.duplicates import detect_duplicates_in_table
from src.profiler.missing import detect_missing_in_table


def test_tiny_duplicates_detector():
    """Test duplicate row and near-duplicate identifier detection on a hand-made DataFrame."""
    # Table with 1 exact duplicate row and 1 near-duplicate order_id
    df = pd.DataFrame({
        "order_id": ["ORD-1", "ORD-2", "ORD-1", "  ord-2  "],
        "amount": [10.0, 20.0, 10.0, 20.0],
    })
    msgs = detect_duplicates_in_table(df, "orders")
    assert len(msgs) == 1
    assert "[DUPLICATES] orders:" in msgs[0]
    assert "1 exact duplicate rows" in msgs[0]
    assert "1 more repeat order_id with differing case/whitespace" in msgs[0]


def test_tiny_currency_detector():
    """Test currency detector on hand-made DataFrame with mixed currencies."""
    df = pd.DataFrame({
        "order_id": ["ORD-1", "ORD-2", "ORD-3"],
        "amount": [100.0, 200.0, 300.0],
        "currency": ["USD", "EUR", "INR"],
    })
    msgs = detect_currency_issues_in_table(df, "orders")
    assert len(msgs) == 1
    assert "[CURRENCY] orders.amount has currency column values {EUR, INR, USD}; amounts are not comparable" in msgs[0]


def test_tiny_dates_detector():
    """Test date format and ambiguity detector on hand-made DataFrame."""
    df = pd.DataFrame({
        "order_id": ["ORD-1", "ORD-2", "ORD-3"],
        "order_date": [
            "2024-01-15",  # ISO
            "25/03/2024",  # Provably DD/MM (25 > 12)
            "05/04/2024",  # Ambiguous (5 and 4 <= 12)
        ],
    })
    msgs = detect_date_issues_in_table(df, "orders")
    assert len(msgs) == 1
    assert "[DATES] orders.order_date: mixed formats; 1 rows provably DD/MM (day>12), 1 ambiguous" in msgs[0]


def test_tiny_missing_detector():
    """Test missing detector on hand-made DataFrame with NaN and sentinel strings."""
    df = pd.DataFrame({
        "order_id": ["ORD-1", "ORD-2", "ORD-3", "ORD-4"],
        "amount": [100.0, np.nan, "N/A", "NA"],
    })
    msgs = detect_missing_in_table(df, "orders")
    assert len(msgs) == 1
    assert "[MISSING] orders.amount:" in msgs[0]
    assert "1 NaN" in msgs[0]
    assert '1 "N/A"' in msgs[0]
    assert '1 "NA"' in msgs[0]


def test_tiny_keys_detector():
    """Test foreign key / orphan detector on tiny parent and child tables."""
    df_customers = pd.DataFrame({
        "customer_id": ["CUST-1", "CUST-2"],
        "name": ["Alice", "Bob"],
    })
    df_orders = pd.DataFrame({
        "order_id": ["ORD-1", "ORD-2", "ORD-3"],
        "customer_id": ["CUST-1", "CUST-999", "CUST-999"],
    })
    dfs = {
        "customers": df_customers,
        "orders": df_orders,
    }
    msgs = detect_key_and_contradiction_issues(dfs)
    assert len(msgs) == 1
    assert "[KEYS] orders.customer_id: 2 values missing from customers.customer_id" in msgs[0]


def test_profile_tables_and_column_integration():
    """Test integrated profile_tables and profile_column on tiny DataFrames."""
    df_customers = pd.DataFrame({
        "customer_id": ["CUST-1", "CUST-2"],
        "name": ["Alice", "Bob"],
    })
    df_orders = pd.DataFrame({
        "order_id": ["ORD-1", "ORD-2", "ORD-1"],
        "customer_id": ["CUST-1", "CUST-999", "CUST-1"],
        "amount": [50.0, "N/A", 50.0],
        "currency": ["USD", "EUR", "USD"],
        "order_date": ["2024-01-01", "25/02/2024", "2024-01-01"],
    })
    dfs = {
        "customers": df_customers,
        "orders": df_orders,
    }

    full_profile = profile_tables(dfs)
    assert "[DUPLICATES]" in full_profile
    assert "[CURRENCY]" in full_profile
    assert "[DATES]" in full_profile
    assert "[MISSING]" in full_profile
    assert "[KEYS]" in full_profile

    col_profile = profile_column(dfs, "orders", "amount")
    assert "[CURRENCY] orders.amount" in col_profile
    assert "[MISSING] orders.amount" in col_profile
