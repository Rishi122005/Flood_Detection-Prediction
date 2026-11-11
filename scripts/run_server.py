#!/usr/bin/env python3
"""Run the local HTTP API and interactive global coordinate globe."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flood_app.server import main


if __name__ == "__main__":
    raise SystemExit(main())
