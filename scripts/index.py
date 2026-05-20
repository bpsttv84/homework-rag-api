#!/usr/bin/env python3
"""Index data/source.md into Qdrant (run from repo root: python scripts/index.py)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.indexing import run_index


def main() -> None:
    n = run_index(get_settings())
    print(f"Indexed {n} chunks into Qdrant.")


if __name__ == "__main__":
    main()
