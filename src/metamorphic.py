"""Metamorphic testing for tabular analysis: row-order permutation invariance.

Data analysis logic that performs aggregations, lookups, or filtering should
generally be invariant to the order of rows in the source tables unless
an explicit sort is performed. A metamorphic check permutes the row order of
all input tables and re-runs the candidate code in the sandbox to detect
unintended order sensitivities (e.g. relying on .iloc[0] without sorting).
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pandas as pd

from src.sandbox import run_code

TOLERANCE_REL: float = 1e-6
TOLERANCE_ABS: float = 1e-9


def check_row_order_invariance(
    code: str,
    data_dir: str | Path,
    original_result: dict[str, int | float | str],
    seed: int = 42,
    timeout: int = 20,
) -> tuple[bool, str | None]:
    """Test if code execution is invariant to shuffling row order in input CSVs.

    Args:
        code: Analysis code to execute.
        data_dir: Directory containing input CSV tables.
        original_result: Expected result dictionary from standard execution.
        seed: Random seed for deterministic row permutation.
        timeout: Subprocess execution timeout in seconds.

    Returns:
        Tuple of (is_invariant: bool, reason_if_failed: str | None).
    """
    data_path = Path(data_dir).resolve()
    if not data_path.is_dir():
        return False, f"Data directory not found: {data_dir}"

    with tempfile.TemporaryDirectory(prefix="metamorphic_data_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Shuffle each CSV file's rows
        for csv_path in sorted(data_path.glob("*.csv")):
            try:
                df = pd.read_csv(csv_path)
                if len(df) > 1:
                    shuffled = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
                else:
                    shuffled = df
                shuffled.to_csv(tmp_path / csv_path.name, index=False)
            except (OSError, ValueError) as exc:
                return False, f"Failed to shuffle {csv_path.name}: {exc}"

        # Re-run code on permuted data
        res = run_code(code, tmp_path, timeout=timeout)
        if not res.ok or res.result is None:
            return False, f"Execution failed on row-shuffled data: {res.error}"

        # Compare outputs
        shuffled_result = res.result
        for k, orig_v in original_result.items():
            if k not in shuffled_result:
                return (
                    False,
                    f"Label '{k}' missing from shuffled execution result (found {list(shuffled_result.keys())})",
                )

            shuf_v = shuffled_result[k]
            matches = False
            if isinstance(orig_v, (int, float)) and isinstance(shuf_v, (int, float)):
                matches = math.isclose(
                    float(orig_v),
                    float(shuf_v),
                    rel_tol=TOLERANCE_REL,
                    abs_tol=TOLERANCE_ABS,
                )
            else:
                matches = str(orig_v) == str(shuf_v)

            if not matches:
                return (
                    False,
                    f"Order-dependent result for '{k}': original was {orig_v!r}, but shuffled data produced {shuf_v!r}",
                )

    return True, None
