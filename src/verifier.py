"""Verification layer for proof-carrying data analysis.

Independent verification re-runs the candidate code in the sandbox against the raw
data tables, asserts that the re-run output matches all reported values within
numerical tolerances, computes content hashes of input data tables, and packages
verifiable proof bundles.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from pydantic import ValidationError

from src.sandbox import run_code
from src.schemas import (
    Answer,
    CrossCheck,
    FinishArgs,
    Proof,
    Refusal,
    TraceStep,
    Verdict,
)

TOLERANCE_REL: float = 1e-6
TOLERANCE_ABS: float = 1e-9


def hash_data_dir(data_dir: str | Path) -> str:
    """Compute deterministic SHA256 digest over sorted CSV file names and byte contents.

    Args:
        data_dir: Directory containing input CSV files.

    Returns:
        Formatted digest string 'sha256:<hex>'.

    Raises:
        FileNotFoundError: If data_dir does not exist or is not a directory.
    """
    d = Path(data_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"Data directory not found: {d}")

    h = hashlib.sha256()
    for p in sorted(d.glob("*.csv"), key=lambda f: f.name):
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes())
    return f"sha256:{h.hexdigest()}"


def finalize(
    question: str,
    finish: FinishArgs,
    last_code: str | None,
    data_dir: str | Path,
    trace: list[TraceStep],
    check_metamorphic: bool = False,
) -> Answer:
    """Finalize analysis output by independently re-executing code and verifying claims.

    Args:
        question: User query string.
        finish: Proposed finish arguments from agent.
        last_code: Python code string from the latest run_code step, or None.
        data_dir: Path to raw data directory.
        trace: Full agent execution history.

    Returns:
        A fully validated Answer schema instance.
    """
    try:
        data_path = Path(data_dir)
        data_hash = hash_data_dir(data_path) if data_path.is_dir() else "sha256:missing"

        # Pass-through for AMBIGUOUS
        if finish.verdict == Verdict.AMBIGUOUS:
            return Answer(
                question=question,
                verdict=Verdict.AMBIGUOUS,
                text=finish.answer_text,
                values=finish.values,
                assumptions=finish.assumptions,
                interpretations=finish.interpretations,
                proof=None,
                refusal=finish.refusal,
                trace=trace,
            )

        # Pass-through for REFUSED
        if finish.verdict == Verdict.REFUSED:
            refusal = finish.refusal or Refusal(reason=finish.answer_text or "Refused by analyst")
            return Answer(
                question=question,
                verdict=Verdict.REFUSED,
                text=finish.answer_text,
                values=[],
                assumptions=finish.assumptions,
                interpretations=finish.interpretations,
                proof=None,
                refusal=refusal,
                trace=trace,
            )

        # Verification for ANSWERED and ANSWERED_WITH_ASSUMPTIONS
        # 1. Enforce assumptions requirement for ANSWERED_WITH_ASSUMPTIONS
        if finish.verdict == Verdict.ANSWERED_WITH_ASSUMPTIONS and not finish.assumptions:
            return Answer(
                question=question,
                verdict=Verdict.REFUSED,
                text="Refused: verdict claimed assumptions were used, but no assumptions were recorded.",
                values=[],
                refusal=Refusal(
                    reason="ANSWERED_WITH_ASSUMPTIONS requires at least one assumption, but none were provided."
                ),
                trace=trace,
            )

        # 2. Check that executable code is provided
        if not last_code:
            return Answer(
                question=question,
                verdict=Verdict.REFUSED,
                text="Refused: no executable code was provided to verify the claimed answer.",
                values=[],
                refusal=Refusal(
                    reason="Cannot verify answer: no code was executed (last_code is None)."
                ),
                trace=trace,
            )

        # 3. Check that values are provided
        if not finish.values:
            return Answer(
                question=question,
                verdict=Verdict.REFUSED,
                text="Refused: no numerical values were reported in finish arguments.",
                values=[],
                refusal=Refusal(
                    reason="Answered verdict requires at least one value in finish.values."
                ),
                trace=trace,
            )

        # 4. Re-run last_code in clean sandbox
        sandbox_res = run_code(last_code, data_dir)
        if not sandbox_res.ok or sandbox_res.result is None:
            err_msg = sandbox_res.error or "Unknown sandbox execution error"
            return Answer(
                question=question,
                verdict=Verdict.REFUSED,
                text=f"Refused: code re-run failed during verification: {err_msg}",
                values=[],
                refusal=Refusal(reason=f"Verification re-run failed: {err_msg}"),
                trace=trace,
            )

        # 5. Check every finish.values label exists and matches rerun result
        rerun_dict = sandbox_res.result
        for v in finish.values:
            if v.label not in rerun_dict:
                available = sorted(rerun_dict.keys())
                return Answer(
                    question=question,
                    verdict=Verdict.REFUSED,
                    text=f"Refused: label '{v.label}' missing from rerun result.",
                    values=[],
                    refusal=Refusal(
                        reason=f"Label '{v.label}' missing from rerun result (available: {available})"
                    ),
                    trace=trace,
                )

            expected_val = v.value
            rerun_val = rerun_dict[v.label]

            matches = False
            if isinstance(expected_val, (int, float)) and isinstance(rerun_val, (int, float)):
                matches = math.isclose(
                    float(expected_val),
                    float(rerun_val),
                    rel_tol=TOLERANCE_REL,
                    abs_tol=TOLERANCE_ABS,
                )
            else:
                matches = str(expected_val) == str(rerun_val)

            if not matches:
                return Answer(
                    question=question,
                    verdict=Verdict.REFUSED,
                    text=f"Refused: value mismatch for '{v.label}'.",
                    values=[],
                    refusal=Refusal(
                        reason=(
                            f"Verification mismatch for label '{v.label}': "
                            f"expected {expected_val!r}, rerun produced {rerun_val!r}"
                        )
                    ),
                    trace=trace,
                )

        # 6. Optional metamorphic check (permutation invariance)
        cross_check = None
        if check_metamorphic:
            from src.metamorphic import check_row_order_invariance

            is_invariant, metam_err = check_row_order_invariance(
                last_code, data_dir, rerun_dict
            )
            cross_check = CrossCheck(agree=is_invariant, path_b_value=None)
            if not is_invariant:
                return Answer(
                    question=question,
                    verdict=Verdict.REFUSED,
                    text=f"Refused: metamorphic check failed: {metam_err}",
                    values=[],
                    refusal=Refusal(reason=f"Metamorphic check failed: {metam_err}"),
                    trace=trace,
                )

        # 7. Build proof and verified answer
        proof = Proof(
            code=last_code,
            language="python",
            data_hash=data_hash,
            rerun_value=rerun_dict,
            reproduced=True,
            cross_check=cross_check,
        )

        return Answer(
            question=question,
            verdict=finish.verdict,
            text=finish.answer_text,
            values=finish.values,
            assumptions=finish.assumptions,
            interpretations=finish.interpretations,
            proof=proof,
            refusal=None,
            trace=trace,
        )

    except (ValidationError, ValueError) as exc:
        # Fallback to guaranteed valid REFUSED answer to prevent invalid schemas escaping
        return Answer(
            question=question,
            verdict=Verdict.REFUSED,
            text=f"Refused: Schema validation error: {exc}",
            values=[],
            refusal=Refusal(reason=f"Schema validation error: {exc}"),
            trace=trace,
        )
