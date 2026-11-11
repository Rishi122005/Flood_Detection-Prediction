#!/usr/bin/env python3
"""Build a compact cache for fast Alipingal demo API responses."""
import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecasting.cwc_level_pilot import HFL_METRES, read_station_series


def build_cache(source: Path, output: Path) -> dict:
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"CWC telemetry CSV not found: {source}")
    series = read_station_series(source, "Alipingal", HFL_METRES)
    if not series:
        raise ValueError("No Alipingal observations passed the documented 0–13.11 m demo screen")
    latest = max(series)
    previous_time = latest - timedelta(hours=24)
    payload = {
        "schema_version": 1,
        "station_id": "alipingal-devi",
        "station_name": "Alipingal / Alipingala, Devi River, Jagatsinghpur, Odisha",
        "source_file": str(source),
        "source_size_bytes": source.stat().st_size,
        "source_mtime_ns": source.stat().st_mtime_ns,
        "timestamp_timezone": "not specified by source; recorded wall-clock time",
        "screen": {"minimum_m": 0, "maximum_m": HFL_METRES,
                   "meaning": "demonstration-only screen based on published historical HFL; above-range readings require CWC QC"},
        "latest_observation": {"observed_at": latest.isoformat(), "level_m": series[latest]},
        "observation_24h_prior": ({"observed_at": previous_time.isoformat(), "level_m": series[previous_time]}
                                  if previous_time in series else None),
        "series_observation_count_after_screen": len(series),
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "data/observations/cwc_mahanadi_telemetry_2021_2025.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/forecasting/alipingal_demo_cache.json")
    args = parser.parse_args()
    result = build_cache(args.csv, args.output)
    print(f"Wrote cache for {result['series_observation_count_after_screen']:,} screened station observations: {args.output}")
    print(f"Latest: {result['latest_observation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
