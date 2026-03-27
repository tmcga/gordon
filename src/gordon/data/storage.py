"""Parquet-based bar storage utilities."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gordon.core.errors import DataError


def save_bars(df: pd.DataFrame, path: Path) -> None:
    """Save a DataFrame of OHLCV bars to a Parquet file.

    Parent directories are created automatically.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow")


def load_bars(path: Path) -> pd.DataFrame:
    """Load a DataFrame of OHLCV bars from a Parquet file."""
    path = Path(path)
    if not path.exists():
        raise DataError(f"Bar file not found: {path}")
    return pd.read_parquet(path, engine="pyarrow")
