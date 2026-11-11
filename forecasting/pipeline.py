"""Fail-closed data preparation for flood onset forecasting.

Rows are labeled only when evidence establishes a flood onset or explicitly
confirms observation coverage throughout the target window. Missing coverage is
unlabeled, never silently interpreted as a non-flood.
"""

from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

HORIZON_HOURS = 24
FEATURES = (
    "rainfall_observed_24h_mm",
    "rainfall_forecast_24h_mm",
    "glofas_discharge_forecast_24h_m3_s",
    "river_level_m",
    "river_danger_level_m",
    "reservoir_storage_mcm",
)
FEATURE_HEADERS = (
    "sample_id", "location_id", "evaluation_group", "issued_at",
    "rainfall_observed_24h_mm", "rainfall_observed_24h_start",
    "rainfall_observed_24h_end", "rainfall_observed_available_at",
    "rainfall_observed_source", "rainfall_forecast_24h_mm",
    "rainfall_forecast_issue_at", "rainfall_forecast_valid_start",
    "rainfall_forecast_valid_end", "rainfall_forecast_source",
    "glofas_forecast_issue_at", "glofas_forecast_valid_start", "glofas_forecast_valid_end",
    "glofas_forecast_source", "glofas_discharge_forecast_24h_m3_s",
    "river_level_m", "river_level_observed_at", "river_level_source",
    "river_danger_level_m", "reservoir_storage_mcm",
    "reservoir_observed_at", "reservoir_source",
)
PREDICTION_HEADERS = tuple(name for name in FEATURE_HEADERS if name not in {"sample_id", "evaluation_group"})
EVENT_HEADERS = ("event_id", "location_id", "event_start", "event_end", "source", "source_url")
COVERAGE_HEADERS = ("location_id", "coverage_start", "coverage_end", "source", "source_url", "coverage_notes")
GLOFAS_EXPORT_HEADERS = ("location_id", "forecast_issued_at", "valid_from", "valid_until",
                         "forecast_horizon_hours", "river_discharge_m3_s", "unit", "record_type", "source_file")
OUTPUT_HEADERS = FEATURE_HEADERS + (
    "label_flood_onset_within_24h", "label_window_start", "label_window_end", "label_evidence_source",
)


class DataError(ValueError):
    """Input data is malformed or violates the forecasting data contract."""


def parse_timestamp(value: str, field: str) -> datetime:
    value = (value or "").strip()
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataError(f"{field} must be an ISO-8601 timestamp with timezone") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise DataError(f"{field} must include a timezone")
    return result.astimezone(timezone.utc)


def finite_number(row: dict[str, str], field: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise DataError(f"{field} must be present and numeric") from exc
    if not math.isfinite(value):
        raise DataError(f"{field} must be finite")
    return value


def validate_feature_row(row: dict[str, str]) -> tuple[datetime, datetime]:
    missing = [key for key in FEATURE_HEADERS if key not in row]
    if missing:
        raise DataError(f"Missing required columns: {', '.join(missing)}")
    for key in ("sample_id", "location_id", "evaluation_group", "rainfall_observed_source",
                "rainfall_forecast_source", "glofas_forecast_source", "river_level_source", "reservoir_source"):
        if not (row.get(key) or "").strip():
            raise DataError(f"{key} must be non-empty")
    issue = parse_timestamp(row["issued_at"], "issued_at")
    end = issue + timedelta(hours=HORIZON_HOURS)
    observed_start = parse_timestamp(row["rainfall_observed_24h_start"], "rainfall_observed_24h_start")
    observed_end = parse_timestamp(row["rainfall_observed_24h_end"], "rainfall_observed_24h_end")
    observed_available = parse_timestamp(row["rainfall_observed_available_at"], "rainfall_observed_available_at")
    forecast_issue = parse_timestamp(row["rainfall_forecast_issue_at"], "rainfall_forecast_issue_at")
    forecast_start = parse_timestamp(row["rainfall_forecast_valid_start"], "rainfall_forecast_valid_start")
    forecast_end = parse_timestamp(row["rainfall_forecast_valid_end"], "rainfall_forecast_valid_end")
    glofas_issue = parse_timestamp(row["glofas_forecast_issue_at"], "glofas_forecast_issue_at")
    glofas_start = parse_timestamp(row["glofas_forecast_valid_start"], "glofas_forecast_valid_start")
    glofas_end = parse_timestamp(row["glofas_forecast_valid_end"], "glofas_forecast_valid_end")
    river_at = parse_timestamp(row["river_level_observed_at"], "river_level_observed_at")
    reservoir_at = parse_timestamp(row["reservoir_observed_at"], "reservoir_observed_at")
    if observed_end > issue or observed_start >= observed_end or observed_available > issue:
        raise DataError("Observed rainfall must cover a completed 24-hour window available by issue time")
    if observed_end - observed_start != timedelta(hours=HORIZON_HOURS):
        raise DataError("Observed rainfall window must be exactly 24 hours")
    if forecast_issue > issue or forecast_start > issue or forecast_end < end:
        raise DataError("Rainfall forecast must be issued by issue time and cover the full target window")
    if glofas_issue > issue or glofas_start > issue or glofas_end < end:
        raise DataError("GloFAS forecast must be issued by issue time and cover the full target window")
    if river_at > issue or reservoir_at > issue:
        raise DataError("River and reservoir observations must be available by issue time")
    for name in FEATURES:
        finite_number(row, name)
    if finite_number(row, "rainfall_observed_24h_mm") < 0 or finite_number(row, "rainfall_forecast_24h_mm") < 0:
        raise DataError("Rainfall measurements must be non-negative")
    if finite_number(row, "glofas_discharge_forecast_24h_m3_s") < 0:
        raise DataError("GloFAS discharge forecast must be non-negative")
    if finite_number(row, "river_level_m") < 0 or finite_number(row, "river_danger_level_m") < 0:
        raise DataError("River levels and danger level must be non-negative")
    if finite_number(row, "reservoir_storage_mcm") < 0:
        raise DataError("Reservoir storage must be non-negative")
    return issue, end


def read_csv(path: Path, required: Iterable[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise DataError(f"Input file not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = set(required) - set(reader.fieldnames or [])
        if missing:
            raise DataError(f"{path} is missing columns: {', '.join(sorted(missing))}")
        return list(reader)


def align_glofas_forecasts(features: list[dict[str, str]], forecasts: list[dict[str, str]]) -> list[dict[str, str]]:
    """Join only issue-time-available GloFAS daily discharge windows to samples."""
    indexed: dict[str, list[dict[str, str]]] = {}
    for item in forecasts:
        if item.get("unit") != "m3 s-1":
            raise DataError("GloFAS export unit must be m3 s-1")
        if item.get("record_type") != "ECMWF control forecast":
            continue
        indexed.setdefault((item.get("location_id") or "").strip(), []).append(item)
    aligned = []
    for feature in features:
        row = dict(feature)
        try:
            issue = parse_timestamp(row.get("issued_at", ""), "issued_at")
            target_end = issue + timedelta(hours=HORIZON_HOURS)
            candidates = []
            for item in indexed.get((row.get("location_id") or "").strip(), []):
                forecast_issue = parse_timestamp(item.get("forecast_issued_at", ""), "forecast_issued_at")
                valid_start = parse_timestamp(item.get("valid_from", ""), "valid_from")
                valid_end = parse_timestamp(item.get("valid_until", ""), "valid_until")
                if forecast_issue <= issue and valid_start <= issue and valid_end >= target_end:
                    candidates.append((forecast_issue, item))
            if candidates:
                _, match = max(candidates, key=lambda pair: pair[0])
                row.update({"glofas_forecast_issue_at": match["forecast_issued_at"],
                            "glofas_forecast_valid_start": match["valid_from"],
                            "glofas_forecast_valid_end": match["valid_until"],
                            "glofas_forecast_source": match.get("source_file", "ECMWF GRIB export"),
                            "glofas_discharge_forecast_24h_m3_s": match["river_discharge_m3_s"]})
            else:
                row.update({"glofas_forecast_issue_at": "", "glofas_forecast_valid_start": "",
                            "glofas_forecast_valid_end": "", "glofas_forecast_source": "",
                            "glofas_discharge_forecast_24h_m3_s": "",
                            "_glofas_alignment_error": "no issue-time-available GloFAS discharge forecast covers the 24-hour target window"})
        except (DataError, KeyError) as exc:
            row["_glofas_alignment_error"] = str(exc)
        aligned.append(row)
    return aligned


def prepare_rows(features: list[dict[str, str]], events: list[dict[str, str]],
                 coverage: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict]:
    parsed_events = []
    for event in events:
        if not event.get("event_id", "").strip() or not event.get("location_id", "").strip():
            raise DataError("Each flood event needs a non-empty event_id and location_id")
        start = parse_timestamp(event["event_start"], "event_start")
        end_text = (event.get("event_end") or "").strip()
        end = parse_timestamp(end_text, "event_end") if end_text else start
        if end < start or not event.get("source", "").strip() or not event.get("source_url", "").strip():
            raise DataError("Each flood event needs valid dates and a documented source/source_url")
        parsed_events.append((event["location_id"].strip(), start, end, event["source"].strip()))
    parsed_coverage = []
    for item in coverage:
        if not item.get("location_id", "").strip():
            raise DataError("Each coverage interval needs a non-empty location_id")
        start = parse_timestamp(item["coverage_start"], "coverage_start")
        end = parse_timestamp(item["coverage_end"], "coverage_end")
        if end < start or not item.get("source", "").strip() or not item.get("source_url", "").strip():
            raise DataError("Coverage intervals need valid dates and a documented source/source_url")
        parsed_coverage.append((item["location_id"].strip(), start, end, item["source"].strip()))

    labeled, skipped = [], {}
    sample_ids = set()
    for row in features:
        try:
            if row.get("_glofas_alignment_error"):
                raise DataError(row["_glofas_alignment_error"])
            issue, target_end = validate_feature_row(row)
            sample_id = row["sample_id"].strip()
            if sample_id in sample_ids:
                raise DataError("sample_id must be unique")
            sample_ids.add(sample_id)
            location = row["location_id"].strip()
            matching = [e for e in parsed_events if e[0] == location]
            if any(start <= issue <= end for _, start, end, _ in matching):
                raise DataError("Flood is already active at issue time; onset forecasting label is undefined")
            onset = [e for e in matching if issue < e[1] <= target_end]
            if onset:
                row = dict(row)
                row.update(label_flood_onset_within_24h="1", label_window_start=issue.isoformat(),
                           label_window_end=target_end.isoformat(),
                           label_evidence_source=";".join(sorted({e[3] for e in onset})))
                labeled.append(row)
                continue
            covered = [c for c in parsed_coverage if c[0] == location and c[1] <= issue and c[2] >= target_end]
            if not covered:
                skipped[sample_id] = "no documented full-window event surveillance coverage"
                continue
            row = dict(row)
            row.update(label_flood_onset_within_24h="0", label_window_start=issue.isoformat(),
                       label_window_end=target_end.isoformat(),
                       label_evidence_source=";".join(sorted({c[3] for c in covered})))
            labeled.append(row)
        except DataError as exc:
            key = (row.get("sample_id") or "<missing sample_id>").strip()
            skipped[key] = str(exc)
    report = {
        "status": "prepared" if labeled else "no_labeled_samples",
        "horizon_hours": HORIZON_HOURS,
        "input_rows": len(features), "labeled_rows": len(labeled),
        "positive_rows": sum(r["label_flood_onset_within_24h"] == "1" for r in labeled),
        "negative_rows": sum(r["label_flood_onset_within_24h"] == "0" for r in labeled),
        "unlabeled_or_invalid_rows": len(skipped), "skipped": skipped,
        "label_policy": "positive requires documented flood onset in (issue, issue+24h]; negative requires documented continuous coverage of the full window and no onset",
    }
    return labeled, report


def prepare_files(features_path: Path, events_path: Path, coverage_path: Path,
                  output_path: Path, report_path: Path, glofas_path: Path | None = None) -> dict:
    features = read_csv(features_path, FEATURE_HEADERS)
    if glofas_path:
        glofas_rows = read_csv(glofas_path, GLOFAS_EXPORT_HEADERS)
        features = align_glofas_forecasts(features, glofas_rows)
    events = read_csv(events_path, EVENT_HEADERS)
    coverage = read_csv(coverage_path, COVERAGE_HEADERS)
    rows, report = prepare_rows(features, events, coverage)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    import json
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
