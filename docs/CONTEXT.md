# Project context (every agent reads this first)

Proof-carrying data analyst agent (HackNex 2026, PSI08). Input: messy multi-table CSV data
plus a question. Output: an answer with re-runnable pandas code, every cleaning assumption
listed, or an honest REFUSED/AMBIGUOUS. The agent proposes; deterministic code verifies.

## Verdicts
ANSWERED: clean data, no assumptions. ANSWERED_WITH_ASSUMPTIONS: cleaned or interpreted data,
each fix logged. AMBIGUOUS: several reasonable interpretations give different values.
REFUSED: data missing, tables contradict, false premise, forecast/cause not supportable.
A wrong confident answer is worse than REFUSED. Unverifiable answers are downgraded to REFUSED.

## Contract (frozen, ask the team before editing)
src/schemas.py (Answer, FinishArgs, Action, parse_action) and src/prompts.py.
Code run by the agent sets `result = {label: number}` using preloaded `dfs` (dict of DataFrames),
`pd`, `np`. No inplace=True.

## Seams (exact signatures)
src/ingest.py     load_tables(data_dir) -> dict[str, pd.DataFrame]
                  body: {p.stem: pd.read_csv(p) for p in sorted(Path(data_dir).glob("*.csv"))}
                  raw load, NO cleaning (cleaning happens in generated code and is logged)
src/profiler/__init__.py
                  profile_tables(dfs) -> str          deterministic data-quality report text
                  profile_column(dfs, table, column) -> str
src/sandbox.py    run_code(code, data_dir, timeout=20) -> SandboxResult
                  SandboxResult(pydantic): ok: bool, result: dict[str, float|int|str]|None,
                  stdout: str, error: str|None
src/verifier.py   hash_data_dir(data_dir) -> str      "sha256:<hex>" over sorted csv bytes
                  finalize(question, finish: FinishArgs, last_code: str|None, data_dir,
                           trace: list[TraceStep]) -> Answer
                  re-runs last_code, compares finish.values to the re-run result, builds Proof;
                  if not reproduced, returns a REFUSED Answer explaining the mismatch
src/proof.py      build_proof_bundle(answer, data_dir, out_dir) -> Path
                  writes standalone proof.py (loads CSVs, runs code, prints result JSON) + manifest
src/agent.py      run_agent(question, data_dir="data/raw", max_steps=8) -> Answer
src/llm.py        chat(messages, json_mode=True) -> str   (Ollama native /api/chat)

## Conventions
Python 3.12, pandas 2.x (<3), pydantic v2, pathlib for paths, type hints, ruff clean.
Explicit error handling (try/except with useful messages), never silent failures.
Only open-source dependencies; no billed APIs; no network calls from project code.
New dependency -> add to requirements.txt and tell the team.
Config via env: LLM_BASE_URL, LLM_MODEL, MAX_STEPS (see .env.example).
Every module gets pytest tests in tests/. Comment the WHY of design choices; the owner must be
able to explain every line at evaluation.
Git: branch per task (heavyA/..., heavyB/..., lightC/..., lightD/...), small commits,
`git pull --rebase origin main` before pushing. Only edit files you own. Shared-file changes
go through the team. Never commit .venv, .env, or model files.
Write docs/NOTES_<role>.md at the end: what works, what is stubbed, known issues.

## Timeline (T+0 = start)
T+0:10 stubs with the exact signatures pushed to main (so everyone can import everything)
T+1:00 Light C pushes dataset + questions; Heavy B pushes working sandbox + verifier
T+1:30 modules ready; Heavy A integrates and runs the agent end to end
T+2:15 FEATURE FREEZE. Then README, sample run, demo recording, rehearsal.

## Stretch backlog (only after the end-to-end demo works)
sensitivity intervals, metamorphic checks, SQL cross-check, interpretation fan-out.
