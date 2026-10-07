from pathlib import Path

import pandas as pd


def load_tables(data_dir: str) -> dict[str, pd.DataFrame]:
    """Raw load, no cleaning. Cleaning happens in generated code so it gets logged."""
    d = Path(data_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"data dir not found: {d}")
    return {p.stem: pd.read_csv(p) for p in sorted(d.glob("*.csv"))}
