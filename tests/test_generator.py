"""Unit tests for dataset generator, determinism, and trap injection."""

from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import pytest

from data.generator.build_dataset import build
from data.generator.clean_data import generate_clean_dataset
from data.generator.traps import inject_traps


def test_clean_generator_determinism():
    """Verify clean dataset is identical for the same seed."""
    ds1 = generate_clean_dataset(seed=42)
    ds2 = generate_clean_dataset(seed=42)

    assert ds1["customers"].equals(ds2["customers"])
    assert ds1["orders"].equals(ds2["orders"])
    assert ds1["fx_rates"].equals(ds2["fx_rates"])


def test_traps_injection_counts():
    """Verify all planted traps match required target counts."""
    clean_dfs = generate_clean_dataset(seed=42)
    raw_dfs, stats = inject_traps(clean_dfs, seed=42)

    assert stats["exact_duplicate_rows"] == 37
    assert stats["near_duplicate_rows"] == 12
    assert stats["orphan_customer_rows"] == 9
    assert stats["provably_dd_mm_dates"] == 140
    assert stats["ambiguous_dates"] == 85
    assert stats["nan_amounts"] == 24
    assert stats["na_string_amounts"] == 6


def test_build_dataset_artifacts(tmp_path: Path):
    """Verify build_dataset creates valid CSVs, data dictionary, and questions."""
    build(seed=42, base_dir=tmp_path)

    raw_dir = tmp_path / "data" / "raw"
    eval_dir = tmp_path / "data" / "eval"

    assert (raw_dir / "customers.csv").exists()
    assert (raw_dir / "orders.csv").exists()
    assert (raw_dir / "fx_rates.csv").exists()
    assert (raw_dir / "data_dictionary.md").exists()
    assert (eval_dir / "questions.jsonl").exists()

    # Verify data dictionary leaves orders.amount unit undocumented
    dict_content = (raw_dir / "data_dictionary.md").read_text(encoding="utf-8")
    assert "amount" in dict_content
    assert "[Undocumented]" in dict_content

    # Verify questions structure
    with open(eval_dir / "questions.jsonl", "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    assert len(questions) == 12
    clean_q = [q for q in questions if not q["traps"]]
    refused_q = [q for q in questions if q["expected_verdict"] == "REFUSED"]
    trap_answered_q = [q for q in questions if q["traps"] and q["expected_verdict"] == "ANSWERED"]

    assert len(clean_q) == 3
    assert len(refused_q) == 4
    assert len(trap_answered_q) == 5

    for q in questions:
        assert "id" in q
        assert "question" in q
        assert "traps" in q
        assert "expected_verdict" in q
        assert "expected_value" in q
        assert "tolerance" in q
        if q["expected_verdict"] == "ANSWERED":
            assert isinstance(q["expected_value"], (int, float))
        else:
            assert q["expected_value"] is None
