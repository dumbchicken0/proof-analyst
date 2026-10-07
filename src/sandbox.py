"""Sandbox execution environment for untrusted data analysis code.

NOTE ON SECURITY:
This sandbox runs user-generated Python code in a dedicated subprocess with
AST pre-screening, monkeypatched sockets, and optional OS resource limits
(RLIMIT_CPU, RLIMIT_AS). This is best-effort defense-in-depth to catch infinite
loops, runaway memory allocations, accidental disk writes, and network calls.
It is NOT an impenetrable security boundary or kernel-level sandbox (e.g. gVisor
or seccomp-bpf container).
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

FORBIDDEN_MODULES: set[str] = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "shutil",
    "requests",
    "urllib",
    "pathlib",
    "importlib",
    "ctypes",
}

FORBIDDEN_FUNCS: set[str] = {
    "open",
    "eval",
    "exec",
    "__import__",
}

STDOUT_STDERR_CHAR_LIMIT: int = 2000
MARKER_START: str = "__SANDBOX_RESULT_START__"
MARKER_END: str = "__SANDBOX_RESULT_END__"


class SandboxResult(BaseModel):
    """Result of executing code in the isolated subprocess sandbox."""

    ok: bool
    result: dict[str, int | float | str] | None = None
    stdout: str = ""
    error: str | None = None
    stderr: str = ""


def validate_code_safety(code: str) -> None:
    """Statically validate that code contains no dangerous imports or calls.

    Raises:
        ValueError: If forbidden imports, functions, or syntax errors are detected.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in submitted code: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module in FORBIDDEN_MODULES:
                    raise ValueError(
                        f"Forbidden import: module '{root_module}' is not allowed in sandbox"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module in FORBIDDEN_MODULES:
                    raise ValueError(
                        f"Forbidden import: importing from '{root_module}' is not allowed in sandbox"
                    )
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_FUNCS:
                raise ValueError(
                    f"Forbidden function call: '{node.func.id}()' is prohibited in sandbox"
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_FUNCS:
                raise ValueError(
                    f"Forbidden attribute call: '{node.func.attr}()' is prohibited in sandbox"
                )
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_FUNCS:
            raise ValueError(
                f"Forbidden identifier: reference to '{node.id}' is prohibited in sandbox"
            )


def _truncate(text: str, limit: int = STDOUT_STDERR_CHAR_LIMIT) -> str:
    """Truncate text to limit characters, appending an indicator if truncated."""
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


_RUNNER_SCRIPT = f"""# Auto-generated sandbox runner
import sys
import json
import math
import traceback
from pathlib import Path

# 1. Block socket access by monkeypatching
try:
    import socket
    def _blocked_socket(*args, **kwargs):
        raise PermissionError("Network socket operations are blocked in sandbox environment")
    socket.socket = _blocked_socket  # type: ignore
    socket.create_connection = _blocked_socket  # type: ignore
except Exception:
    pass

# 2. Apply resource limits (CPU time and memory) where supported (Unix/macOS)
try:
    import resource
    # RLIMIT_CPU: 25 seconds soft, 30 seconds hard limit
    resource.setrlimit(resource.RLIMIT_CPU, (25, 30))
    # RLIMIT_AS: 2 GB memory address space limit if supported
    mem_limit = 2 * 1024 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
except (ImportError, AttributeError, ValueError, OSError):
    pass

try:
    # 3. Read execution payload
    with open("payload.json", "r", encoding="utf-8") as f:
        payload = json.load(f)
    code = payload["code"]
    data_dir = payload["data_dir"]

    # 4. Load CSVs with the exact one-liner from ingest.load_tables
    import pandas as pd
    import numpy as np

    d = Path(data_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"data dir not found: {{d}}")
    dfs = {{p.stem: pd.read_csv(p) for p in sorted(d.glob("*.csv"))}}

    # 5. Execute user code in scope with dfs, pd, np
    scope = {{"dfs": dfs, "pd": pd, "np": np}}
    exec(code, scope)

    # 6. Extract and validate result variable
    if "result" not in scope:
        raise ValueError("Code executed successfully but did not set the 'result' variable")
    raw_result = scope["result"]
    if not isinstance(raw_result, dict) or len(raw_result) == 0:
        raise ValueError("Variable 'result' must be a non-empty dict of str -> int/float/str")

    cleaned_result = {{}}
    for k, v in raw_result.items():
        if not isinstance(k, str):
            raise TypeError(f"Result key '{{k}}' must be a string, got {{type(k).__name__}}")

        # Convert numpy scalars to native Python types
        if isinstance(v, (np.integer, np.floating, np.bool_)):
            v = v.item()

        # Reject NaN, Inf, and non-scalar types
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"Result value for '{{k}}' is invalid: NaN and Inf are not allowed")
        elif not isinstance(v, (int, str)):
            raise TypeError(
                f"Result value for '{{k}}' must be int, float, or str, got {{type(v).__name__}}"
            )
        cleaned_result[k] = v

    # 7. Print result preceded and succeeded by markers
    print("\\n{MARKER_START}")
    print(json.dumps(cleaned_result))
    print("{MARKER_END}")
    sys.exit(0)

except Exception:
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
"""


def run_code(code: str, data_dir: str | Path, timeout: int = 20) -> SandboxResult:
    """Run data analysis code in an isolated subprocess.

    Args:
        code: Python source code string to execute.
        data_dir: Path to directory containing CSV data tables.
        timeout: Maximum seconds before terminating the subprocess.

    Returns:
        SandboxResult containing status, parsed result dict, stdout, and errors.
    """
    # Step 1: Pre-execution static AST check
    try:
        validate_code_safety(code)
    except ValueError as exc:
        err_msg = str(exc)
        return SandboxResult(
            ok=False,
            result=None,
            stdout="",
            error=err_msg,
            stderr=err_msg,
        )

    # Step 2: Validate data directory exists
    data_path = Path(data_dir).resolve()
    if not data_path.is_dir():
        err_msg = f"Data directory not found: {data_dir}"
        return SandboxResult(
            ok=False,
            result=None,
            stdout="",
            error=err_msg,
            stderr=err_msg,
        )

    # Step 3: Run child process in a temporary working directory
    with tempfile.TemporaryDirectory(prefix="sandbox_run_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        payload_file = tmp_path / "payload.json"
        runner_file = tmp_path / "_runner.py"

        payload: dict[str, Any] = {
            "code": code,
            "data_dir": str(data_path),
        }
        payload_file.write_text(json.dumps(payload), encoding="utf-8")
        runner_file.write_text(_RUNNER_SCRIPT, encoding="utf-8")

        try:
            proc = subprocess.run(
                [sys.executable, str(runner_file)],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout_str = _truncate(exc.stdout or "")
            stderr_str = _truncate(exc.stderr or "")
            return SandboxResult(
                ok=False,
                result=None,
                stdout=stdout_str,
                error=f"Execution timed out after {timeout} seconds",
                stderr=stderr_str,
            )

    raw_stdout = proc.stdout
    raw_stderr = proc.stderr

    # Step 4: Parse marker from output
    if proc.returncode != 0:
        err_msg = _truncate(raw_stderr.strip()) or f"Process failed with exit code {proc.returncode}"
        return SandboxResult(
            ok=False,
            result=None,
            stdout=_truncate(raw_stdout),
            error=err_msg,
            stderr=_truncate(raw_stderr),
        )

    if MARKER_START not in raw_stdout or MARKER_END not in raw_stdout:
        return SandboxResult(
            ok=False,
            result=None,
            stdout=_truncate(raw_stdout),
            error="Execution succeeded but output marker was not found",
            stderr=_truncate(raw_stderr),
        )

    try:
        parts = raw_stdout.split(MARKER_START, 1)
        user_stdout = parts[0].strip()
        json_block = parts[1].split(MARKER_END, 1)[0].strip()
        parsed_result = json.loads(json_block)
    except (IndexError, json.JSONDecodeError) as exc:
        return SandboxResult(
            ok=False,
            result=None,
            stdout=_truncate(raw_stdout),
            error=f"Failed to decode sandbox result JSON: {exc}",
            stderr=_truncate(raw_stderr),
        )

    return SandboxResult(
        ok=True,
        result=parsed_result,
        stdout=_truncate(user_stdout),
        error=None,
        stderr=_truncate(raw_stderr),
    )
