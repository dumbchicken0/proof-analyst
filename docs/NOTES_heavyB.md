# Heavy B — Execution & Verification Layer Notes

## Overview
This document covers the implementation, design decisions, and status of the execution and verification layer for the **Proof-Carrying Data Analyst** (HackNex 2026, Problem Statement HNX26PSI08).

Owner role: `heavyB`
Owned modules:
- `src/ingest.py`
- `src/sandbox.py`
- `src/verifier.py`
- `src/proof.py`
- `src/metamorphic.py` (stretch goal)
- `tests/test_sandbox.py`
- `tests/test_verifier.py`
- `tests/test_proof.py`
- `tests/test_metamorphic.py`
- `docs/NOTES_heavyB.md`

---

## Architecture & Design Decisions (The "Why")

### 1. `src/sandbox.py` (Subprocess Execution & Best-Effort Isolation)
- **Subprocess Isolation (`sys.executable`, temp directory, hard timeout)**:
  - *Why*: Executing untrusted or LLM-generated code in the parent agent process risks mutating agent memory, leaving dangling open handles, hanging the event loop indefinitely, or polluting globals. Running in a subprocess ensures that memory, thread pools, and process state can be cleanly terminated via `timeout` without affecting the analyst engine.
  - *Why temp directory*: The child runs in a freshly minted `tempfile.TemporaryDirectory` rather than the project root. This ensures that any accidental file creation by user code does not overwrite repository files.
- **Payload Passing via `payload.json`**:
  - *Why*: Passing Python source code via command-line arguments (`-c "..."`) is vulnerable to OS argument buffer limits (e.g., `ARG_MAX`) and shell quoting differences between POSIX shells and Windows `cmd.exe`/PowerShell. Passing a structured JSON file guarantees identical behavior across macOS, Linux, and Windows.
- **AST Pre-Screening (`validate_code_safety`)**:
  - *Why*: Before even spawning a subprocess, static AST analysis inspects import statements (`ast.Import`, `ast.ImportFrom`), function calls (`ast.Call`), and identifiers (`ast.Name`, `ast.Attribute`). Forbidden modules (`os`, `sys`, `subprocess`, `socket`, `shutil`, `requests`, `urllib`, `pathlib`, `importlib`, `ctypes`) and dangerous builtins (`open`, `eval`, `exec`, `__import__`) are rejected with explicit, friendly error messages. This prevents trivial resource access and provides instant feedback without paying the subprocess startup latency.
- **In-Child Defense-in-Depth**:
  - *Socket monkeypatching*: Sockets are monkeypatched in the child script (`socket.socket`, `socket.create_connection`) to raise `PermissionError` if invoked.
  - *Resource limits*: `resource.setrlimit(RLIMIT_CPU, ...)` and `resource.setrlimit(RLIMIT_AS, ...)` are applied where available (macOS/Linux) and guarded with `try / except (ImportError, AttributeError, ValueError, OSError)` so Windows runs without error.
  - *Security Disclaimer*: This isolation is defense-in-depth against accidental side effects, not a kernel-grade security boundary (e.g. gVisor/seccomp). This is clearly documented in module docstrings.
- **Result Contract & Conversion**:
  - *Why*: The contract dictates that user code sets a `result` variable that is a non-empty `dict[str, int | float | str]`.
  - NumPy scalar types (`np.int64`, `np.float64`, etc.) are converted to standard Python primitives via `.item()`.
  - `NaN` and `Inf` values are rejected immediately with descriptive errors, as NaN math fails equality tests and represents unhandled missing data.
- **Marker Separation & Truncation**:
  - Output uses `__SANDBOX_RESULT_START__` and `__SANDBOX_RESULT_END__` markers to isolate the result JSON from any intermediate `print()` output the analyst code generated.
  - Both stdout and stderr are truncated to 2000 characters to prevent memory explosion if the agent prints enormous tables.

---

### 2. `src/verifier.py` (Deterministic Verification & Ground-Truth Matching)
- **Data Fingerprinting (`hash_data_dir`)**:
  - Computes `sha256:<hex>` over lexicographically sorted CSV filenames and raw bytes.
  - *Why*: Ensures that the exact dataset version used during analysis is bound to the generated proof. Any upstream change or file corruption immediately invalidates the proof hash.
- **Independent Re-execution in `finalize`**:
  - *Why*: In a proof-carrying system, the verifier never trusts the agent's claim about what the code did. It takes `last_code`, launches it in a fresh sandbox against the data directory, and parses the independent output.
- **Numerical Tolerance**:
  - *Why*: Floating point operations can produce subtle platform variations (e.g., `3.0000000000000004` vs `3.0`). We enforce `math.isclose(expected, actual, rel_tol=1e-6, abs_tol=1e-9)`. String and exact integer matches are compared directly.
- **Explanatory Refusals**:
  - If code re-run fails, if `last_code` is missing, if a label is missing, or if values differ, `finalize` returns a valid `REFUSED` Answer where `Refusal.reason` details the exact mismatch (e.g., expected 999.0 vs rerun 300.0).
- **Enforcing Assumptions Contract**:
  - `ANSWERED_WITH_ASSUMPTIONS` submitted without any assumptions is automatically downgraded to `REFUSED`, preventing ungrounded assumptions claims.
- **Schema Safety Guarantee**:
  - `finalize` wraps `Answer` construction in `try / except (ValidationError, ValueError)`. If any schema violation occurs, it catches the error and returns a well-formed `REFUSED` answer with the error reason, ensuring an invalid schema instance never escapes.

---

### 3. `src/proof.py` (Self-Contained Proof Bundles)
- **Portability**:
  - `build_proof_bundle(answer, data_dir, out_dir)` creates an independent folder containing:
    1. `data/`: Complete copy of the input CSV tables.
    2. `manifest.json`: Metadata capturing question, verdict, claimed values, and data hash.
    3. `proof.py`: Completely self-contained script requiring only `pandas` and standard library.
  - *Why*: A third party or evaluator should not need to install the whole project repo or understand the agent loop to verify an answer. They can simply run `python proof.py` in the bundle directory.
- **Standalone Execution Flow**:
  - `proof.py` loads `./data/*.csv`, runs the verified code, prints the output JSON, verifies tolerances against `EXPECTED`, and outputs `"REPRODUCED"` (exit 0) or `"MISMATCH"` (exit 1).

---

### 4. `src/metamorphic.py` (Permutation Invariance / Metamorphic Testing)
- **Why**: Many common data analyst bugs involve relying on implicit row order (e.g., using `.iloc[0]` instead of sorting by date/id first, or relying on non-deterministic merges).
- **Mechanism**: Permutes all rows across all input CSV tables (preserving headers) and re-runs the code in the sandbox. If the result changes, it flags an order sensitivity bug.
- **Integration**: Connected to `finalize` via an optional `check_metamorphic=True` parameter that checks order invariance and records the result in `proof.cross_check`.

---

## Test Coverage Summary

All tests are automated with `pytest` and pass 100%:
- `tests/test_sandbox.py` (10 tests):
  - Valid code execution and dict output
  - NumPy scalar type unboxing
  - Hard timeout termination (`while True: pass` terminated within 1s)
  - Static AST rejection of 10 forbidden modules (`os`, `sys`, `subprocess`, `socket`, `pathlib`, `shutil`, `requests`, `urllib`, `ctypes`, `importlib`)
  - Static AST rejection of forbidden calls (`open`, `eval`, `exec`, `__import__`)
  - NaN result rejection
  - Inf result rejection
  - Empty dict result rejection
  - Missing result variable rejection
  - User stdout capture up to marker
- `tests/test_verifier.py` (9 tests):
  - Deterministic SHA256 data directory hashing and mutation detection
  - Exact match verification (ANSWERED)
  - Numerical value mismatch detection and explanatory refusal
  - Missing label detection and explanatory refusal
  - Missing code (`last_code=None`) refusal
  - `ANSWERED_WITH_ASSUMPTIONS` valid verification
  - `ANSWERED_WITH_ASSUMPTIONS` empty assumptions downgrade to `REFUSED`
  - `AMBIGUOUS` pass-through with interpretations
  - `REFUSED` pass-through with refusal details
- `tests/test_proof.py` (3 tests):
  - End-to-end proof bundle generation and independent subprocess execution
  - Tampering detection (modifying bundle data triggers `"MISMATCH"` and exit 1)
  - Rejection of proof bundle creation when proof is missing
- `tests/test_metamorphic.py` (3 tests):
  - Order-invariant code verification
  - Order-sensitive code detection (`iloc[0]` fragility flagged)
  - Integration with `finalize(..., check_metamorphic=True)`

Total test count across project: **27 passed in ~7.5s**.

---

## Status & What Works
- [x] `src/ingest.py`: Clean raw table loader (`load_tables`).
- [x] `src/sandbox.py`: Hardened subprocess sandbox with AST checks, timeout, marker parsing.
- [x] `src/verifier.py`: Ground-truth verification, dataset hashing, tolerant matching, schema safety.
- [x] `src/proof.py`: Standalone verifiable proof bundle generator.
- [x] `src/metamorphic.py`: Tabular metamorphic row-order testing.
- [x] Full test suite (Mac & Windows compatible, no network, ruff clean).

## Stubbed / Out-of-Scope (Owned by Teammates)
- `src/agent.py`: Agent ReAct execution loop (owned by Heavy A).
- `src/llm.py`: Ollama API client (owned by Heavy A).
- `src/profiler/`: Table and column data profiling (owned by Light D).
- `data/`: Evaluation datasets and synthetic benchmarks (owned by Light C).

## Known Gaps & Future Enhancements
1. **Memory Limits on macOS / Windows**: `resource.setrlimit(RLIMIT_AS)` is POSIX-specific and has platform-dependent behavior on macOS; on Windows, memory limits could be enhanced using Windows Job Objects if needed.
2. **SQL Cross-Check**: The `CrossCheck` schema supports comparing Pandas code against an alternative SQL engine (e.g. DuckDB). The foundation is laid for Light/Heavy agents to plug in SQL cross-checking into `finalize`.
