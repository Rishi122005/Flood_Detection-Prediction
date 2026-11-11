"""Cleaning and descriptive spatial summaries for DesInventar event records.

This module intentionally does not create non-event labels or a future-risk
probability. DesInventar contains reported events, not exposure-normalized
surveillance of event and non-event periods.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


NUMERIC_FIELDS = (
    "Records", "Deaths", "Injured", "Missing", "Houses Destroyed",
    "Houses Damaged", "Directly affected", "Indirectly Affected", "Relocated",
    "Evacuated", "Losses $USD", "Losses $Local", "Duration (d)",
)
OUTPUT_FIELDS = (
    "event_id", "country", "admin1", "admin2", "event_date", "event_year",
    "event_month", "date_precision", "latitude", "longitude", "geocode_method",
    "coordinate_source", *[f"impact_{field.lower().replace(' ', '_').replace('$', '')}"
                             for field in NUMERIC_FIELDS],
)


class HistoricalEventIndex:
    """Lightweight spatial index over cleaned reported events."""

    def __init__(self, path: Path):
        self.path = path
        self.cells: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
        self.count = 0
        if not path.is_file():
            return
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                try:
                    lat, lon = float(row["latitude"]), float(row["longitude"])
                except (KeyError, TypeError, ValueError):
                    continue
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                row["_latitude"] = lat  # type: ignore[assignment]
                row["_longitude"] = lon  # type: ignore[assignment]
                self.cells[(math.floor(lat), math.floor(lon))].append(row)
                self.count += 1

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371.0088
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp, dl = p2 - p1, math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * radius * math.asin(min(1.0, math.sqrt(a)))

    def nearby(self, latitude: float, longitude: float, radius_km: float = 25.0,
               limit: int = 10) -> dict[str, Any]:
        if not self.count:
            return {"status": "unavailable", "reason": "Cleaned historical event dataset is unavailable."}
        if not (math.isfinite(radius_km) and 1 <= radius_km <= 100):
            raise ValueError("historical event radius_km must be between 1 and 100")
        lat_span = int(math.ceil(radius_km / 110.5)) + 1
        cos_lat = max(0.01, abs(math.cos(math.radians(latitude))))
        lon_span = min(180, int(math.ceil(radius_km / (110.5 * cos_lat))) + 1)
        candidates = []
        for lat_cell in range(max(-90, math.floor(latitude) - lat_span),
                              min(90, math.floor(latitude) + lat_span) + 1):
            for lon_offset in range(-lon_span, lon_span + 1):
                lon_cell = ((math.floor(longitude) + lon_offset + 180) % 360) - 180
                for row in self.cells.get((lat_cell, lon_cell), ()):
                    distance = self._distance_km(latitude, longitude, row["_latitude"], row["_longitude"])
                    if distance <= radius_km:
                        candidates.append((distance, row))
        candidates.sort(key=lambda item: item[0])
        public = []
        for distance, row in candidates[:limit]:
            public.append({key: value for key, value in {
                "event_id": row.get("event_id"), "distance_km": round(distance, 3),
                "latitude": round(row["_latitude"], 5), "longitude": round(row["_longitude"], 5),
                "country": row.get("country"), "admin1": row.get("admin1"),
                "admin2": row.get("admin2"), "event_date": row.get("event_date") or None,
                "event_year": row.get("event_year") or None,
                "date_precision": row.get("date_precision"),
                "geocode_method": row.get("geocode_method"),
            }.items() if value not in (None, "")})
        return {
            "status": "available" if candidates else "no_nearby_records",
            "reason": None if candidates else "No report point is within the search radius; this presence-only catalogue does not prove that no flood occurred.",
            "source": "DesInventar_Geocoded.csv",
            "dataset_record_count": self.count, "radius_km": radius_km,
            "nearby_report_count": len(candidates), "returned_records": len(public),
            "results": public,
            "interpretation": "Historical reported-event records near the query point; representative geocodes may be administrative centroids. Count is not exposure-normalized risk or a future-event probability.",
        }


def _date_parts(value: str, today: date | None = None) -> tuple[str, str, str, str]:
    """Return ISO date/year/month/precision; zero components remain unknown."""
    today = today or date.today()
    value = (value or "").strip()
    try:
        parts = value.split("/")
        if len(parts) != 3:
            return "", "", "", "unknown"
        if len(parts[0]) == 4:
            year, month, day = (int(p) for p in parts)
        else:
            month, day, year = (int(p) for p in parts)
        if not 1 <= year <= today.year or month < 0 or month > 12 or day < 0 or day > 31:
            return "", "", "", "invalid"
        y = f"{year:04d}"
        if month == 0:
            return "", y, "", "year"
        m = f"{month:02d}"
        if day == 0:
            return "", y, m, "month"
        try:
            parsed = date(year, month, day)
        except ValueError:
            return "", y, m, "month_invalid_day"
        return parsed.isoformat(), y, m, "day"
    except (ValueError, TypeError):
        return "", "", "", "invalid"


def _number(value: str | None) -> str:
    if value is None or not value.strip():
        return ""
    try:
        result = float(value.replace(",", "").strip())
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(result) or result < 0:
        return ""
    return str(int(result)) if result.is_integer() else str(result)


def clean_desinventar(source: Path, output: Path, report_path: Path,
                      hotspot_path: Path, today: date | None = None) -> dict[str, Any]:
    """Clean source records and emit descriptive 1-degree record-count bins."""
    if not source.is_file():
        raise FileNotFoundError(f"DesInventar CSV does not exist: {source}")
    today = today or date.today()
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    hotspot_path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, ...]] = set()
    stats: Counter[str] = Counter()
    countries: Counter[str] = Counter()
    geo_methods: Counter[str] = Counter()
    years: list[int] = []
    coordinate_bounds = [math.inf, math.inf, -math.inf, -math.inf]
    bins: Counter[tuple[int, int]] = Counter()
    unique_locations: set[tuple[float, float]] = set()
    sample_rows: list[dict[str, str]] = []
    required = {"Country", "Adm1", "Adm2", "Date", "GEO_LAT", "GEO_LON", "GEO_METHOD"}
    with source.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
        with output.open("w", newline="", encoding="utf-8") as clean_stream:
            writer = csv.DictWriter(clean_stream, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            for source_row, row in enumerate(reader, 2):
                stats["input_rows"] += 1
                full_key = tuple((row.get(name) or "").strip() for name in reader.fieldnames or [])
                if full_key in seen:
                    stats["exact_duplicate_rows_removed"] += 1
                    continue
                seen.add(full_key)
                try:
                    lat, lon = float(row["GEO_LAT"]), float(row["GEO_LON"])
                except (TypeError, ValueError):
                    stats["invalid_geocoded_coordinates"] += 1
                    continue
                if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                    stats["invalid_geocoded_coordinates"] += 1
                    continue
                coordinate_bounds[0] = min(coordinate_bounds[0], lat)
                coordinate_bounds[1] = min(coordinate_bounds[1], lon)
                coordinate_bounds[2] = max(coordinate_bounds[2], lat)
                coordinate_bounds[3] = max(coordinate_bounds[3], lon)
                iso_date, year, month, precision = _date_parts(row.get("Date", ""), today)
                stats[f"date_precision_{precision}"] += 1
                if not year:
                    stats["records_without_usable_year"] += 1
                else:
                    years.append(int(year))
                method = (row.get("GEO_METHOD") or "unknown").strip()
                geo_methods[method] += 1
                coordinate_source = "GEO_LAT/GEO_LON (source-provided geocoding)"
                clean = {
                    "event_id": f"desinventar_row_{source_row}",
                    "country": (row.get("Country") or "").strip(),
                    "admin1": (row.get("Adm1") or "").strip(),
                    "admin2": (row.get("Adm2") or "").strip(),
                    "event_date": iso_date, "event_year": year, "event_month": month,
                    "date_precision": precision, "latitude": f"{lat:.8f}",
                    "longitude": f"{lon:.8f}", "geocode_method": method,
                    "coordinate_source": coordinate_source,
                }
                for name in NUMERIC_FIELDS:
                    clean[f"impact_{name.lower().replace(' ', '_').replace('$', '')}"] = _number(row.get(name))
                writer.writerow(clean)
                stats["usable_rows"] += 1
                countries[clean["country"] or "unknown"] += 1
                unique_locations.add((round(lat, 5), round(lon, 5)))
                # Spatial counts describe report density only, not event probability.
                bins[(math.floor(lat), math.floor(lon))] += 1
                if len(sample_rows) < 10:
                    sample_rows.append(clean)

    hotspot_fields = ("latitude_bin_south", "longitude_bin_west", "latitude_bin_north",
                      "longitude_bin_east", "reported_event_records")
    with hotspot_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=hotspot_fields)
        writer.writeheader()
        for (lat_bin, lon_bin), count in sorted(bins.items()):
            writer.writerow({"latitude_bin_south": lat_bin, "longitude_bin_west": lon_bin,
                             "latitude_bin_north": lat_bin + 1, "longitude_bin_east": lon_bin + 1,
                             "reported_event_records": count})
    report = {
        "status": "completed" if stats["usable_rows"] else "no_usable_rows",
        "source": str(source), "source_bytes": source.stat().st_size,
        "cleaned_output": str(output), "hotspot_output": str(hotspot_path),
        "input_rows": stats["input_rows"], "usable_rows": stats["usable_rows"],
        "exact_duplicate_rows_removed": stats["exact_duplicate_rows_removed"],
        "invalid_geocoded_coordinates": stats["invalid_geocoded_coordinates"],
        "date_precision_counts": {key.removeprefix("date_precision_"): value
                                  for key, value in stats.items() if key.startswith("date_precision_")},
        "records_without_usable_year": stats["records_without_usable_year"],
        "historical_year_range": [min(years), max(years)] if years else None,
        "coordinate_bounds_south_west_north_east": coordinate_bounds if stats["usable_rows"] else None,
        "coordinate_bounds_note": "Bounding rectangle of reported geocodes, not continuous coverage of every location inside it.",
        "countries": len(countries), "country_record_counts": dict(countries.most_common()),
        "unique_rounded_locations_5dp": len(unique_locations), "one_degree_report_count_bins": len(bins),
        "geocode_method_counts": dict(geo_methods.most_common()),
        "source_columns": list(reader.fieldnames or []),
        "event_description_columns": [name for name in (reader.fieldnames or [])
                                       if any(token in name.casefold() for token in
                                              ("description", "event type", "disaster type", "comments", "event name"))],
        "original_LAT_LON_note": "Ignored for coordinates because source GEO_LAT/GEO_LON fields are supplied and validated; original LAT/LON contain out-of-range entries.",
        "normalization": "Impact values parsed as non-negative numeric values; missing/invalid values remain empty, never imputed. Coordinates use the supplied GEO_LAT/GEO_LON fields.",
        "analysis_scope": "Historical reported-event lookup and 1-degree record-density counts only. Counts are not exposure-normalized risk, not event probability, and not a forecast.",
        "limitations": [
            "Records are presence-only event reports; no complete non-event surveillance intervals or exposure denominators.",
            "GEO_METHOD includes administrative centroids and fuzzy administrative matches; points are representative geocodes, not flood boundaries.",
            "Date precision varies; zero month/day values are retained as partial dates and excluded from exact-date fields.",
            "Impacts are post-event outcomes and are not used as predictors.",
        ],
        "sample_cleaned_rows": sample_rows,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report

