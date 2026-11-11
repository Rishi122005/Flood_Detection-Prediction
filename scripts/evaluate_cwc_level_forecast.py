#!/usr/bin/env python3
"""Run a lightweight chronological 24-hour continuous river-level pilot."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecasting.cwc_level_pilot import HFL_METRES, evaluate, read_station_series


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "data/observations/cwc_mahanadi_telemetry_2021_2025.csv")
    parser.add_argument("--station", default="Alipingal")
    parser.add_argument("--upper-level-m", type=float, default=HFL_METRES,
                        help="conservative data-quality screen; default is CWC listed Alipingal historical HFL")
    parser.add_argument("--json", type=Path, default=ROOT / "reports/level_forecast_pilot.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "reports/level_forecast_pilot.md")
    args = parser.parse_args()
    if not args.csv.is_file():
        parser.error(f"CWC source CSV not found: {args.csv}")
    series = read_station_series(args.csv, args.station, args.upper_level_m)
    result = evaluate(series)
    result.update({"station": args.station, "source_csv": str(args.csv),
                   "upper_level_screen_m": args.upper_level_m,
                   "timestamp_timezone": "not specified by source; naive wall-clock timestamps retained",
                   "method": "duplicate timestamps median-collapsed; exact hourly lag availability required; one issue per midnight per day; target t+24h; split by calendar year; Ridge standardized using training data only; persistence predicts current level",
                   "flood_threshold_model_trained": False})
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    md = ["# CWC river-level regression pilot", "",
          "**Diagnostic continuous-level regression only; this is not a flood prediction.**", "",
          f"- Station: {args.station} (CWC Mahanadi telemetry)",
          f"- Source timestamps: timezone unspecified; treated as naive recorded wall-clock values",
          f"- Quality screen: retained levels from 0 through {args.upper_level_m:g} m. This is a conservative screen based on the published historical HFL, not a claim that higher values are impossible.",
          "- Features: gauge level at issue and differences from exactly 1, 6, and 24 hours before issue.",
          "- Target: observed gauge level exactly 24 hours after issue.",
          "- Split: train 2021, validation 2022, test 2023; no random split; no artifact persisted.",
          f"- Counts by year: `{json.dumps(result.get('split', {}), sort_keys=True)}`", ""]
    if "ridge" in result:
        md += [f"- Independent test windows: {result['split']['2023']}",
               f"- Test target range: {result['test_target_range_m'][0]:.6f}–{result['test_target_range_m'][1]:.6f} m",
               f"- Persistence MAE/RMSE: {result['persistence']['mae_m']:.9f} / {result['persistence']['rmse_m']:.9f} m",
               f"- Ridge MAE/RMSE: {result['ridge']['mae_m']:.9f} / {result['ridge']['rmse_m']:.9f} m",
               f"- Ridge better than persistence by MAE: {result['ridge_better_than_persistence']}", ""]
    md += [f"Assessment: {result.get('reason', '')}", "",
           "This pilot excludes readings above the historical-HFL screen because their provenance is unresolved. CWC must confirm whether these are corrupt, datum/encoding errors, or genuine new extremes. The 2023 test sample is too small and narrow-stage to support deployment. The model is not integrated into the dashboard and no flood probability is produced.", ""]
    args.markdown.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
