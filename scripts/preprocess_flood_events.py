#!/usr/bin/env python3
"""Clean DesInventar event records and write descriptive hotspot counts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecasting.desinventar import clean_desinventar


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/floodevents/DesInventar_Geocoded.csv")
    parser.add_argument("--cleaned", type=Path, default=ROOT / "outputs/flood_events/desinventar_cleaned.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "outputs/flood_events/preprocessing_report.json")
    parser.add_argument("--hotspots", type=Path, default=ROOT / "outputs/flood_events/historical_1deg_record_counts.csv")
    args = parser.parse_args()
    try:
        report = clean_desinventar(args.input, args.cleaned, args.report, args.hotspots)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({key: report[key] for key in (
        "status", "input_rows", "usable_rows", "exact_duplicate_rows_removed",
        "invalid_geocoded_coordinates", "historical_year_range", "countries",
        "unique_rounded_locations_5dp", "one_degree_report_count_bins",
    )}, indent=2))
    model_status_path = ROOT / "outputs/flood_events/model_status.json"
    model_status_path.parent.mkdir(parents=True, exist_ok=True)
    model_status = {
        "status": "not_trained",
        "target": None,
        "probability": None,
        "decision": "historical descriptive event-report lookup and 1-degree record counts only",
        "reason": "The source is presence-only reported disasters without continuous observed non-event coverage or exposure denominators. Available impact fields are post-event outcomes and are not valid predictors of future occurrence.",
        "source_dataset": str(args.input),
        "usable_event_records": report["usable_rows"],
        "required_for_future_occurrence_model": [
            "Timestamped predictors available before each forecast issue time",
            "Observed flood onset labels matched to the prediction location and horizon",
            "Documented non-event surveillance covering complete target windows",
            "Exposure/geographic support and independent chronological spatial or event-grouped evaluation",
        ],
    }
    model_status_path.write_text(json.dumps(model_status, indent=2) + "\n", encoding="utf-8")
    print(f"Cleaned data: {args.cleaned}\nReport: {args.report}\nDescriptive bins: {args.hotspots}")
    print(f"Forecast model status: {model_status_path} (not trained)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
