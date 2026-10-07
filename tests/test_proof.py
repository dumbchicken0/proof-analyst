"""Tests for standalone proof bundle generation and execution."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.proof import build_proof_bundle
from src.schemas import Answer, Proof, Value, Verdict


@pytest.fixture
def sample_setup():
    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as out_dir:
        src_path = Path(src_dir)
        out_path = Path(out_dir)

        df = pd.DataFrame({"product": ["A", "B", "C"], "sales": [15, 25, 35]})
        df.to_csv(src_path / "sales.csv", index=False)

        yield src_path, out_path


def test_build_proof_bundle_round_trip(sample_setup):
    src_path, out_path = sample_setup

    code = """
total_sales = float(dfs['sales']['sales'].sum())
result = {'total_sales': total_sales}
"""
    answer = Answer(
        question="What are total sales?",
        verdict=Verdict.ANSWERED,
        text="Total sales are 75.",
        values=[Value(label="total_sales", value=75.0)],
        proof=Proof(
            code=code,
            data_hash="sha256:dummyhash",
            rerun_value={"total_sales": 75.0},
            reproduced=True,
        ),
    )

    bundle_dir = build_proof_bundle(answer, src_path, out_path / "bundle1")
    assert bundle_dir.is_dir()
    assert (bundle_dir / "data" / "sales.csv").is_file()
    assert (bundle_dir / "manifest.json").is_file()
    assert (bundle_dir / "proof.py").is_file()

    # Validate manifest.json contents
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["question"] == "What are total sales?"
    assert manifest["verdict"] == "ANSWERED"
    assert manifest["data_hash"] == "sha256:dummyhash"
    assert len(manifest["values"]) == 1
    assert manifest["values"][0]["label"] == "total_sales"
    assert manifest["values"][0]["value"] == 75.0

    # Execute proof.py with subprocess in an independent environment
    proc = subprocess.run(
        [sys.executable, str(bundle_dir / "proof.py")],
        cwd=bundle_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "REPRODUCED" in proc.stdout
    # Verify printed JSON output before REPRODUCED
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    json_line = lines[-2]  # line before REPRODUCED
    parsed_json = json.loads(json_line)
    assert parsed_json == {"total_sales": 75.0}


def test_proof_bundle_tampered_data_fails(sample_setup):
    src_path, out_path = sample_setup

    code = """
total_sales = float(dfs['sales']['sales'].sum())
result = {'total_sales': total_sales}
"""
    answer = Answer(
        question="What are total sales?",
        verdict=Verdict.ANSWERED,
        text="Total sales are 75.",
        values=[Value(label="total_sales", value=75.0)],
        proof=Proof(
            code=code,
            data_hash="sha256:dummyhash",
            rerun_value={"total_sales": 75.0},
            reproduced=True,
        ),
    )

    bundle_dir = build_proof_bundle(answer, src_path, out_path / "bundle2")

    # Tamper with the CSV data inside the bundle
    tampered_df = pd.DataFrame({"product": ["A"], "sales": [999]})
    tampered_df.to_csv(bundle_dir / "data" / "sales.csv", index=False)

    # Re-run proof.py; it must fail and output MISMATCH
    proc = subprocess.run(
        [sys.executable, str(bundle_dir / "proof.py")],
        cwd=bundle_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "MISMATCH" in proc.stderr or "MISMATCH" in proc.stdout


def test_build_proof_bundle_without_proof_raises(sample_setup):
    src_path, out_path = sample_setup

    answer = Answer(
        question="Unanswerable question?",
        verdict=Verdict.REFUSED,
        text="Data not available.",
        refusal={"reason": "Missing tables"},
    )

    with pytest.raises(ValueError, match="no proof"):
        build_proof_bundle(answer, src_path, out_path / "bundle3")
