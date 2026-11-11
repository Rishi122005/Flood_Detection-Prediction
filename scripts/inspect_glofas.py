#!/usr/bin/env python3
"""Inspect the local GloFAS GRIB2 files without changing or downloading data."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecasting.glofas import GlofasError, write_inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path,
                        help="GRIB2 inputs (default: data/glofas/data.grib and data/glofas/data1.grib)")
    parser.add_argument("--output", type=Path, default=Path("outputs/forecasting/glofas_inventory.json"))
    args = parser.parse_args()
    files = args.files or [Path("data/glofas/data.grib"), Path("data/glofas/data1.grib")]
    try:
        report = write_inventory(files, args.output)
    except (GlofasError, OSError, ValueError) as exc:
        parser.error(str(exc))
    for item in report["files"]:
        print(f"{item['path']}: {item['bitmap_inventory']['message_count']} messages, "
              f"PDT={item['product_definition_templates']}, "
              f"reference={item['reference_time_range']}, valid={item['valid_time_range']}, "
              f"grid={item['grid']['width']}x{item['grid']['height']} {item['grid']['crs']}")
    print(f"Inventory saved: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
