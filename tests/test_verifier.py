"""Tests for verifier module: hash_data_dir and finalize."""
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.schemas import (
    Assumption,
    FinishArgs,
    Interpretation,
    Refusal,
    TraceStep,
    Value,
    Verdict,
)
from src.verifier import finalize, hash_data_dir


@pytest.fixture
def sample_data():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        df_orders = pd.DataFrame({"id": [1, 2], "amount": [100.0, 200.0]})
        df_orders.to_csv(p / "orders.csv", index=False)
        yield p


def test_hash_data_dir(sample_data):
    h1 = hash_data_dir(sample_data)
    assert h1.startswith("sha256:")
    assert len(h1) == 7 + 64

    # Hash should be deterministic
    h2 = hash_data_dir(sample_data)
    assert h1 == h2

    # Mutating data changes hash
    df_extra = pd.DataFrame({"id": [3], "amount": [50.0]})
    df_extra.to_csv(sample_data / "extra.csv", index=False)
    h3 = hash_data_dir(sample_data)
    assert h1 != h3


def test_finalize_match(sample_data):
    code = """
total = float(dfs['orders']['amount'].sum())
result = {'total_amount': total}
"""
    finish = FinishArgs(
        verdict=Verdict.ANSWERED,
        answer_text="Total amount is 300.",
        values=[Value(label="total_amount", value=300.0)],
    )
    trace = [TraceStep(step=1, tool="run_code", observation="ok")]

    answer = finalize(
        question="What is total amount?",
        finish=finish,
        last_code=code,
        data_dir=sample_data,
        trace=trace,
    )

    assert answer.verdict == Verdict.ANSWERED
    assert answer.proof is not None
    assert answer.proof.reproduced is True
    assert answer.proof.rerun_value == {"total_amount": 300.0}
    assert answer.proof.data_hash.startswith("sha256:")
    assert answer.refusal is None
    assert len(answer.trace) == 1


def test_finalize_mismatch(sample_data):
    code = """
total = float(dfs['orders']['amount'].sum())
result = {'total_amount': total}  # sum is 300.0
"""
    finish = FinishArgs(
        verdict=Verdict.ANSWERED,
        answer_text="Total amount is 999.",
        values=[Value(label="total_amount", value=999.0)],
    )

    answer = finalize(
        question="What is total amount?",
        finish=finish,
        last_code=code,
        data_dir=sample_data,
        trace=[],
    )

    assert answer.verdict == Verdict.REFUSED
    assert answer.proof is None
    assert answer.refusal is not None
    assert "verification mismatch" in answer.refusal.reason.lower()
    assert "999" in answer.refusal.reason


def test_finalize_missing_label(sample_data):
    code = """
result = {'sum': 300.0}
"""
    finish = FinishArgs(
        verdict=Verdict.ANSWERED,
        answer_text="Total amount is 300.",
        values=[Value(label="non_existent_label", value=300.0)],
    )

    answer = finalize(
        question="What is total?",
        finish=finish,
        last_code=code,
        data_dir=sample_data,
        trace=[],
    )

    assert answer.verdict == Verdict.REFUSED
    assert answer.refusal is not None
    assert "missing from rerun result" in answer.refusal.reason.lower()


def test_finalize_no_last_code(sample_data):
    finish = FinishArgs(
        verdict=Verdict.ANSWERED,
        answer_text="Claimed answer without code.",
        values=[Value(label="val", value=10.0)],
    )

    answer = finalize(
        question="What is val?",
        finish=finish,
        last_code=None,
        data_dir=sample_data,
        trace=[],
    )

    assert answer.verdict == Verdict.REFUSED
    assert answer.refusal is not None
    assert "last_code is none" in answer.refusal.reason.lower()


def test_finalize_answered_with_assumptions(sample_data):
    code = """
result = {'total': 300.0}
"""
    assumptions = [
        Assumption(
            id="A1",
            type="dedupe",
            detail="Deduped rows",
            evidence="Removed duplicate order IDs",
        )
    ]
    finish = FinishArgs(
        verdict=Verdict.ANSWERED_WITH_ASSUMPTIONS,
        answer_text="Total is 300 with assumptions.",
        values=[Value(label="total", value=300.0)],
        assumptions=assumptions,
    )

    answer = finalize(
        question="What is total?",
        finish=finish,
        last_code=code,
        data_dir=sample_data,
        trace=[],
    )

    assert answer.verdict == Verdict.ANSWERED_WITH_ASSUMPTIONS
    assert answer.proof is not None
    assert answer.proof.reproduced is True
    assert len(answer.assumptions) == 1


def test_finalize_assumptions_downgrade(sample_data):
    code = """
result = {'total': 300.0}
"""
    # Verdict claims assumptions, but assumptions list is empty
    finish = FinishArgs(
        verdict=Verdict.ANSWERED_WITH_ASSUMPTIONS,
        answer_text="Total is 300.",
        values=[Value(label="total", value=300.0)],
        assumptions=[],
    )

    answer = finalize(
        question="What is total?",
        finish=finish,
        last_code=code,
        data_dir=sample_data,
        trace=[],
    )

    assert answer.verdict == Verdict.REFUSED
    assert answer.refusal is not None
    assert "at least one assumption" in answer.refusal.reason.lower()


def test_finalize_ambiguous(sample_data):
    finish = FinishArgs(
        verdict=Verdict.AMBIGUOUS,
        answer_text="The date format is ambiguous.",
        interpretations=[
            Interpretation(label="interpretation_a", value=100.0),
            Interpretation(label="interpretation_b", value=200.0),
        ],
        refusal=Refusal(reason="Ambiguous date column"),
    )

    answer = finalize(
        question="Which date was it?",
        finish=finish,
        last_code=None,
        data_dir=sample_data,
        trace=[],
    )

    assert answer.verdict == Verdict.AMBIGUOUS
    assert len(answer.interpretations) == 2
    assert answer.refusal is not None


def test_finalize_refused(sample_data):
    finish = FinishArgs(
        verdict=Verdict.REFUSED,
        answer_text="Data is missing required revenue column.",
        refusal=Refusal(reason="Revenue column missing", missing=["revenue"]),
    )

    answer = finalize(
        question="What is revenue?",
        finish=finish,
        last_code=None,
        data_dir=sample_data,
        trace=[],
    )

    assert answer.verdict == Verdict.REFUSED
    assert answer.refusal is not None
    assert answer.refusal.missing == ["revenue"]
