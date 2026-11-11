"""Memory-bounded audit of CWC station-level hourly water-level CSV files."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

TIMESTAMP_FORMATS = ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
EXPECTED_COLUMNS = {
    "station": "Station", "agency": "Agency", "river": "River", "basin": "Basin",
    "latitude": "Latitude", "longitude": "Longitude", "timestamp": "Data Acquisition Time",
    "level": "River Water Level Telemetry Hourly (meter)",
}


def parse_observation_time(value: str) -> datetime | None:
    value = (value or "").strip()
    for fmt in TIMESTAMP_FORMATS:
        try:
            # Source CSV carries no timezone field or documentation. Preserve
            # its recorded wall-clock timestamp instead of asserting UTC.
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def _number(value: str) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def audit_cwc_csv(path: Path, report_path: Path | None = None) -> dict[str, Any]:
    """Stream a CSV and report schema, station coverage, gaps, and data quality.

    The source file is read sequentially. If it is not ordered by station and
    timestamp, a temporary on-disk SQLite index computes exact duplicate and
    gap statistics without keeping observation rows in memory.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"CWC telemetry CSV not found: {path}")

    stations: dict[str, dict[str, Any]] = {}
    missing = Counter()
    types: dict[str, Counter] = {}
    sample_limit = 5_000
    total = invalid_timestamps = invalid_levels = invalid_coords = 0
    danger_columns: list[str] = []
    ordered = True
    previous_sort_key: tuple[str, datetime] | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        absent = [name for name in EXPECTED_COLUMNS.values() if name not in columns]
        if absent:
            raise ValueError("CSV is missing expected fields: " + ", ".join(absent))
        danger_columns = [c for c in columns if any(k in c.casefold() for k in ("danger", "warning", "alert level"))]
        for name in columns:
            types[name] = Counter()
        for row in reader:
            total += 1
            for column in columns:
                value = (row.get(column) or "").strip()
                if not value:
                    missing[column] += 1
                if total <= sample_limit and value:
                    if column == EXPECTED_COLUMNS["timestamp"]:
                        types[column]["datetime"] += int(parse_observation_time(value) is not None)
                        types[column]["text"] += int(parse_observation_time(value) is None)
                    else:
                        numeric = _number(value)
                        types[column]["number" if numeric is not None else "text"] += 1

            station = (row.get(EXPECTED_COLUMNS["station"]) or "").strip()
            agency = (row.get(EXPECTED_COLUMNS["agency"]) or "").strip()
            district = (row.get("District") or "").strip()
            river = (row.get(EXPECTED_COLUMNS["river"]) or "").strip()
            key = " | ".join((station, agency, district, river))
            stat = stations.setdefault(key, {
                "station": station, "agency": agency, "district": district, "river": river,
                "basins": set(), "coordinates": set(), "rows": 0, "valid_timestamps": 0,
                "invalid_timestamps": 0, "valid_levels": 0, "invalid_levels": 0,
                "negative_level_values": 0, "valid_observations": 0,
                "missing_levels": 0, "level_min_m": None, "level_max_m": None,
                "zero_gauge_values": set(), "mean_sea_level_values": set(),
                "level_delta_from_zero_gauge_min_m": None,
                "level_delta_from_zero_gauge_max_m": None,
                "level_delta_over_10m_count": 0,
                "first_observation": None, "last_observation": None,
                "valid_coordinate_rows": 0, "_last_time": None, "_duplicates": 0,
                "_gaps": 0, "_longest_gap_hours": 0.0, "_sum_gap_hours": 0.0,
                "_interval_counts": Counter(), "_unique_hour_count": 0,
            })
            stat["rows"] += 1
            stat["basins"].add((row.get(EXPECTED_COLUMNS["basin"]) or "").strip())
            zero_gauge = _number(row.get("RL_of_zeroGauge", ""))
            mean_sea_level = _number(row.get("MeanSeaLevel", ""))
            if zero_gauge is not None:
                stat["zero_gauge_values"].add(zero_gauge)
            if mean_sea_level is not None:
                stat["mean_sea_level_values"].add(mean_sea_level)
            lat = _number(row.get(EXPECTED_COLUMNS["latitude"], ""))
            lon = _number(row.get(EXPECTED_COLUMNS["longitude"], ""))
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0, 0):
                stat["coordinates"].add((lat, lon))
                stat["valid_coordinate_rows"] += 1
            else:
                invalid_coords += 1
            level_text = (row.get(EXPECTED_COLUMNS["level"]) or "").strip()
            level = _number(level_text) if level_text else None
            if level_text:
                if level is None:
                    stat["invalid_levels"] += 1
                    invalid_levels += 1
                else:
                    stat["valid_levels"] += 1
                    stat["negative_level_values"] += int(level < 0)
                    stat["level_min_m"] = level if stat["level_min_m"] is None else min(level, stat["level_min_m"])
                    stat["level_max_m"] = level if stat["level_max_m"] is None else max(level, stat["level_max_m"])
                    if zero_gauge is not None:
                        delta = level - zero_gauge
                        old_min = stat["level_delta_from_zero_gauge_min_m"]
                        old_max = stat["level_delta_from_zero_gauge_max_m"]
                        stat["level_delta_from_zero_gauge_min_m"] = delta if old_min is None else min(delta, old_min)
                        stat["level_delta_from_zero_gauge_max_m"] = delta if old_max is None else max(delta, old_max)
                        stat["level_delta_over_10m_count"] += int(abs(delta) > 10)
            else:
                stat["missing_levels"] += 1

            observed = parse_observation_time(row.get(EXPECTED_COLUMNS["timestamp"], ""))
            if observed is None:
                stat["invalid_timestamps"] += 1
                invalid_timestamps += 1
                continue
            stat["valid_timestamps"] += 1
            if level is None:
                continue
            stat["valid_observations"] += 1
            stat["first_observation"] = observed if stat["first_observation"] is None else min(observed, stat["first_observation"])
            stat["last_observation"] = observed if stat["last_observation"] is None else max(observed, stat["last_observation"])
            sort_key = (key, observed)
            if previous_sort_key is not None and sort_key < previous_sort_key:
                ordered = False
            previous_sort_key = sort_key
            prev = stat["_last_time"]
            if prev is not None:
                delta_h = (observed - prev).total_seconds() / 3600
                if delta_h == 0:
                    stat["_duplicates"] += 1
                elif delta_h == 0.5:
                    stat["_interval_counts"]["30-minute"] += 1
                elif delta_h == 1:
                    stat["_interval_counts"]["1-hour"] += 1
                elif 0 < delta_h < 1:
                    stat["_interval_counts"]["other sub-hour"] += 1
                elif delta_h > 1:
                    stat["_gaps"] += 1
                    stat["_longest_gap_hours"] = max(stat["_longest_gap_hours"], delta_h)
                    stat["_sum_gap_hours"] += delta_h - 1
            stat["_last_time"] = observed
            if prev is None or observed.replace(minute=0, second=0, microsecond=0) != prev.replace(minute=0, second=0, microsecond=0):
                stat["_unique_hour_count"] += 1

    if total == 0:
        raise ValueError("CSV contains a header but no observation rows")

    # For unordered input, compute exact interval statistics from a temporary
    # SQLite index, keeping temporary data on disk rather than in Python RAM.
    if not ordered:
        with tempfile.TemporaryDirectory(prefix="cwc-audit-") as temp:
            db = sqlite3.connect(str(Path(temp) / "timestamps.sqlite"))
            db.execute("CREATE TABLE obs (site TEXT NOT NULL, ts INTEGER NOT NULL, PRIMARY KEY(site, ts)) WITHOUT ROWID")
            batch = []
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    dt = parse_observation_time(row.get(EXPECTED_COLUMNS["timestamp"], ""))
                    level = _number(row.get(EXPECTED_COLUMNS["level"], ""))
                    if dt is None or level is None:
                        continue
                    site = " | ".join(((row.get(EXPECTED_COLUMNS["station"]) or "").strip(),
                                       (row.get(EXPECTED_COLUMNS["agency"]) or "").strip(),
                                       (row.get("District") or "").strip(),
                                       (row.get(EXPECTED_COLUMNS["river"]) or "").strip()))
                    naive_epoch = datetime(1970, 1, 1)
                    batch.append((site, int((dt - naive_epoch).total_seconds())))
                    if len(batch) >= 20_000:
                        db.executemany("INSERT OR IGNORE INTO obs VALUES (?, ?)", batch)
                        batch.clear()
                if batch:
                    db.executemany("INSERT OR IGNORE INTO obs VALUES (?, ?)", batch)
            db.commit()
            for key, in db.execute("SELECT DISTINCT site FROM obs"):
                stat = stations[key]
                times = db.execute("SELECT ts FROM obs WHERE site=? ORDER BY ts", (key,))
                previous = None
                gaps = duplicates = longest = missing_hours = 0
                interval_counts = Counter()
                for (timestamp,) in times:
                    if previous is not None:
                        delta = (timestamp - previous) / 3600
                        if delta > 1:
                            gaps += 1
                            longest = max(longest, delta)
                        elif delta == 0.5:
                            interval_counts["30-minute"] += 1
                        elif delta == 1:
                            interval_counts["1-hour"] += 1
                        elif delta > 0:
                            interval_counts["other sub-hour"] += 1
                    previous = timestamp
                unique_hours = db.execute("SELECT COUNT(DISTINCT ts / 3600) FROM obs WHERE site=?", (key,)).fetchone()[0]
                first_ts, last_ts = db.execute("SELECT MIN(ts), MAX(ts) FROM obs WHERE site=?", (key,)).fetchone()
                expected_hours = last_ts // 3600 - first_ts // 3600 + 1 if first_ts is not None else 0
                missing_hours = max(0, expected_hours - unique_hours)
                duplicates = stat["valid_observations"] - db.execute("SELECT COUNT(*) FROM obs WHERE site=?", (key,)).fetchone()[0]
                stat.update(_gaps=gaps, _duplicates=duplicates,
                            _longest_gap_hours=longest, _sum_gap_hours=missing_hours,
                            _interval_counts=interval_counts, _unique_hour_count=unique_hours)
            db.close()

    normalized = []
    for stat in stations.values():
        first, last = stat["first_observation"], stat["last_observation"]
        span = last.replace(minute=0, second=0, microsecond=0) - first.replace(minute=0, second=0, microsecond=0) if first and last else None
        expected = int(span.total_seconds() / 3600) + 1 if span is not None else 0
        unique_valid = max(0, stat["valid_observations"] - stat["_duplicates"])
        stat_out = {k: v for k, v in stat.items() if not k.startswith("_")}
        stat_out.update({
            "basins": sorted(x for x in stat["basins"] if x),
            "zero_gauge_values_m": sorted(stat["zero_gauge_values"]),
            "mean_sea_level_values_m": sorted(stat["mean_sea_level_values"]),
            "coordinates": [{"latitude": a, "longitude": b} for a, b in sorted(stat["coordinates"])],
            "coordinate_consistent": len(stat["coordinates"]) == 1,
            "duplicate_timestamps": stat["_duplicates"],
            "gap_intervals_over_1h": stat["_gaps"],
            "total_missing_hours_inside_span": stat["_sum_gap_hours"],
            "longest_interval_hours": stat["_longest_gap_hours"],
            "expected_hourly_records_in_span": expected,
            "unique_recorded_hour_buckets": stat["_unique_hour_count"] or unique_valid,
            "interval_cadence_counts": dict(stat["_interval_counts"]),
            "hourly_coverage_pct": round(100 * (stat["_unique_hour_count"] or unique_valid) / expected, 3) if expected else None,
            "first_observation": first.isoformat() if first else None,
            "last_observation": last.isoformat() if last else None,
            "water_level_negative_values": stat["negative_level_values"],
            "danger_level_in_source": bool(danger_columns),
        })
        normalized.append(stat_out)
    normalized.sort(key=lambda x: (x["basins"], -(x["hourly_coverage_pct"] or 0), -x["valid_levels"]))
    for station in normalized:
        station["station_selection"] = "not selected: station-specific threshold and data quality need review"
    if normalized:
        normalized[0]["station_selection"] = (
            "coverage leader only; not selected for threshold prediction (no verified RAJIM threshold, long gaps, and large excursions need CWC clarification)"
        )

    first_all = min((s["first_observation"] for s in normalized if s["first_observation"]), default=None)
    last_all = max((s["last_observation"] for s in normalized if s["last_observation"]), default=None)
    result = {
        "source_file": str(path), "file_size_bytes": path.stat().st_size,
        "timestamp_timezone": "not specified in source; timestamps are naive recorded wall-clock values",
        "record_count": total, "station_count": len(normalized), "csv_columns": columns,
        "observation_time_start": first_all,
        "observation_time_end": last_all,
        "inferred_types_from_first_5000_rows": {k: dict(v) for k, v in types.items()},
        "missing_values_by_column": {k: missing.get(k, 0) for k in columns},
        "invalid_timestamp_rows": invalid_timestamps, "invalid_water_level_rows": invalid_levels,
        "invalid_coordinate_rows": invalid_coords, "rows_ordered_by_station_and_time": ordered,
        "negative_water_level_rows": sum(s["water_level_negative_values"] for s in normalized),
        "duplicate_timestamp_rows": sum(s["duplicate_timestamps"] for s in normalized),
        "gap_intervals_over_1h": sum(s["gap_intervals_over_1h"] for s in normalized),
        "danger_or_warning_level_columns": danger_columns,
        "threshold_status": "no danger/warning threshold column in CSV; station-specific thresholds must be researched separately",
        "stations": normalized,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
        md_path = report_path.with_suffix(".md")
        md_path.write_text(render_markdown(result), encoding="utf-8")
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = ["# CWC Mahanadi telemetry dataset audit", "", f"Source: `{result['source_file']}` ({result['file_size_bytes']:,} bytes).",
             "", "## Dataset summary", "", f"- Records: {result['record_count']:,}",
             f"- Station keys (station, agency, district, river): {result['station_count']}",
             f"- Valid observation period: {result['observation_time_start']} to {result['observation_time_end']}",
             f"- Invalid timestamps: {result['invalid_timestamp_rows']:,}",
             f"- Invalid water-level values: {result['invalid_water_level_rows']:,}",
             f"- Negative numeric water levels: {result['negative_water_level_rows']:,}",
             f"- Invalid or missing coordinates: {result['invalid_coordinate_rows']:,}",
             f"- Duplicate station/timestamp records: {result['duplicate_timestamp_rows']:,}",
             f"- Inter-observation gaps over one hour: {result['gap_intervals_over_1h']:,}",
             f"- Source has danger/warning threshold columns: {'yes' if result['danger_or_warning_level_columns'] else 'no'}",
             "", "Water-level units are identified as metres in the CSV header. The source does not specify the timestamp timezone; timestamps are retained as naive recorded wall-clock values. The file contains observed water levels only; it does not establish forecast issue time or a verified urban flood-event target.",
             "", "## Stations", "", "| Station | District | Basin | Coordinates (lat, lon) | Valid rows | First | Last | Hourly coverage | Cadence intervals | Gap intervals | Longest gap (h) | Level min–max (m) | RL of zero gauge (m) | Readings >10m from RL-zero | Candidate decision |",
             "|---|---|---|---|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|"]
    for s in result["stations"]:
        coordinates = "; ".join(f"{c['latitude']:.6f}, {c['longitude']:.6f}" for c in s["coordinates"])
        levels = f"{s['level_min_m']}–{s['level_max_m']}" if s["level_min_m"] is not None else "unavailable"
        zero_gauge = ", ".join(str(v) for v in s["zero_gauge_values_m"]) or "unavailable"
        coords = "; ".join(f"{c['latitude']:.6f}, {c['longitude']:.6f}" for c in s["coordinates"]) or "unavailable"
        cadence = ", ".join(f"{k}: {v:,}" for k, v in sorted(s["interval_cadence_counts"].items())) or "not classified"
        lines.append(f"| {s['station']} | {s['district']} | {', '.join(s['basins'])} | {coords} | {s['valid_observations']:,} | {s['first_observation']} | {s['last_observation']} | {s['hourly_coverage_pct']}% | {cadence} | {s['gap_intervals_over_1h']:,} | {s['longest_interval_hours']} | {levels} | {zero_gauge} | {s['level_delta_over_10m_count']:,} | {s['station_selection']} |")
    lines.extend(["", "## Assessment and candidate selection", "",
                  "Coverage ranks identify stations for review only. A high record count or hourly coverage does not establish station reliability or flood occurrence. Negative threshold labels also require complete observations throughout the forecast window. Source timestamps carry no timezone declaration; they are preserved as naive recorded wall-clock values.",
                  "", "RAJIM is the coverage leader but is not selected for threshold prediction: its station-specific threshold is not verified here, and it has long gaps and level excursions far above its reported `RL_of_zeroGauge`. Separately, official CWC/Odisha sources publish Alipingal warning/danger/HFL levels; see `reports/cwc_threshold_research.md`. Alipingal's local telemetry contains unresolved readings above that historical HFL, so no threshold model is currently defensible.",
                  "", "`RL_of_zeroGauge` and `MeanSeaLevel` are metadata, not danger thresholds. Threshold exceedance at a river gauge is not equivalent to urban inundation.", ""])
    return "\n".join(lines)
