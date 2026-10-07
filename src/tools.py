"""Deterministic tools exposed to the analyst agent."""

from src.ingest import load_tables
from src.profiler import profile_column, profile_tables


def inspect_schema(data_dir: str) -> str:
    dfs = load_tables(data_dir)
    return profile_tables(dfs)


def sample_rows(data_dir: str, table: str, n: int = 5) -> str:
    dfs = load_tables(data_dir)
    if table not in dfs:
        raise ValueError(f"unknown table: {table}")
    return dfs[table].head(n).to_string()


def profile_column_tool(data_dir: str, table: str, column: str) -> str:
    dfs = load_tables(data_dir)
    return profile_column(dfs, table, column)


def run_code(data_dir: str, code: str):
    from src.sandbox import run_code as sandbox_run_code

    return sandbox_run_code(code, data_dir)
