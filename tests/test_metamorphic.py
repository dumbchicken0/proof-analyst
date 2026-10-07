"""Tests for metamorphic row permutation checks."""
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.metamorphic import check_row_order_invariance
from src.schemas import FinishArgs, Value, Verdict
from src.verifier import finalize


@pytest.fixture
def sequence_data():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        df = pd.DataFrame({"id": [1, 2, 3, 4, 5], "val": [10.0, 50.0, 20.0, 40.0, 30.0]})
        df.to_csv(p / "data.csv", index=False)
        yield p


def test_metamorphic_invariant_code(sequence_data):
    code = """
total = float(dfs['data']['val'].sum())
result = {'total': total}
"""
    is_inv, err = check_row_order_invariance(code, sequence_data, {"total": 150.0})
    assert is_inv is True
    assert err is None


def test_metamorphic_order_sensitive_code(sequence_data):
    # Code takes the first item without sorting, which is fragile to row ordering
    code = """
first_val = float(dfs['data']['val'].iloc[0])
result = {'first_val': first_val}
"""
    is_inv, err = check_row_order_invariance(code, sequence_data, {"first_val": 10.0})
    assert is_inv is False
    assert "order-dependent" in err.lower()


def test_finalize_with_metamorphic_check(sequence_data):
    # Invariant code passes finalize with check_metamorphic=True
    code = """
total = float(dfs['data']['val'].sum())
result = {'total': total}
"""
    finish = FinishArgs(
        verdict=Verdict.ANSWERED,
        answer_text="Total is 150.",
        values=[Value(label="total", value=150.0)],
    )

    answer = finalize(
        question="What is total?",
        finish=finish,
        last_code=code,
        data_dir=sequence_data,
        trace=[],
        check_metamorphic=True,
    )
    assert answer.verdict == Verdict.ANSWERED
    assert answer.proof is not None
    assert answer.proof.cross_check is not None
    assert answer.proof.cross_check.agree is True

    # Order-sensitive code gets refused when check_metamorphic=True
    fragile_code = """
first_val = float(dfs['data']['val'].iloc[0])
result = {'first_val': first_val}
"""
    fragile_finish = FinishArgs(
        verdict=Verdict.ANSWERED,
        answer_text="First value is 10.",
        values=[Value(label="first_val", value=10.0)],
    )

    refused_answer = finalize(
        question="What is first val?",
        finish=fragile_finish,
        last_code=fragile_code,
        data_dir=sequence_data,
        trace=[],
        check_metamorphic=True,
    )
    assert refused_answer.verdict == Verdict.REFUSED
    assert refused_answer.refusal is not None
    assert "metamorphic check failed" in refused_answer.refusal.reason.lower()
