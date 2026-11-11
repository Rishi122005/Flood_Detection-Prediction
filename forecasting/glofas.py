"""Read-only GloFAS GRIB inventory and point-query helpers using GDAL/Rasterio."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path

import rasterio
from rasterio.windows import Window


PARAMETERS = {
    (1, 0, 7): {
        "name": "Discharge from rivers or streams",
        "short_name": "dis",
        "unit": "m3 s-1",
        "parameter_id": 240013,
    }
}
LOCAL_PRODUCT_TEMPLATES = {
    72: "ECMWF local product definition; field semantics are not described by the installed GDAL metadata",
    73: "ECMWF local product definition; interval fields are exposed as raw template numbers by GDAL",
}


class GlofasError(ValueError):
    """Invalid, unsupported, or unreadable GloFAS data/query."""


def _parse_datetime(text: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _product_valid_time(raw_values: str, template: int) -> datetime | None:
    """Extract interval-end date bytes seen in ECMWF local PDT 72/73.

    The positions are only used for those local templates and are validated as
    calendar dates. For other/unknown templates, no valid time is guessed.
    """
    try:
        values = [int(value) for value in raw_values.split()]
        start = {72: 30, 73: 33}.get(template)
        if start is None or len(values) < start + 7:
            return None
        year = values[start] * 256 + values[start + 1]
        month, day, hour, minute, second = values[start + 2:start + 7]
        if not 1900 <= year <= 2100:
            return None
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _scan_grib_bitmaps(path: Path) -> dict:
    """Count records and bitmap-valid points without decoding packed values."""
    records, bitmap_hashes, previous_bitmap, messages = [], {}, None, 0
    with path.open("rb") as stream:
        while True:
            start = stream.tell()
            header = stream.read(16)
            if not header:
                break
            if len(header) != 16 or header[:4] != b"GRIB" or header[7] != 2:
                raise GlofasError(f"Invalid/truncated GRIB2 message header at byte {start}")
            total_length = int.from_bytes(header[8:16], "big")
            if total_length < 20 or start + total_length > path.stat().st_size:
                raise GlofasError(f"Invalid message length at byte {start}: {total_length}")
            points = None
            bitmap = None
            indicator = None
            position = start + 16
            message_end = start + total_length
            while position < message_end - 4:
                stream.seek(position)
                section_header = stream.read(5)
                if len(section_header) != 5:
                    raise GlofasError(f"Truncated section at byte {position}")
                section_length = int.from_bytes(section_header[:4], "big")
                section_number = section_header[4]
                if section_length < 5 or position + section_length > message_end:
                    raise GlofasError(f"Invalid section length at byte {position}")
                if section_number == 3:
                    stream.seek(position + 6)
                    point_bytes = stream.read(4)
                    points = int.from_bytes(point_bytes, "big")
                elif section_number == 6:
                    stream.seek(position + 5)
                    indicator_byte = stream.read(1)
                    if len(indicator_byte) != 1:
                        raise GlofasError("Truncated bitmap indicator")
                    indicator = indicator_byte[0]
                    bitmap_length = section_length - 6
                    bitmap = stream.read(bitmap_length) if indicator == 0 else None
                    if indicator == 0 and len(bitmap or b"") != bitmap_length:
                        raise GlofasError("Truncated explicit bitmap")
                position += section_length
            stream.seek(message_end - 4)
            if stream.read(4) != b"7777":
                raise GlofasError(f"Missing GRIB terminator at byte {message_end - 4}")
            if points is None:
                raise GlofasError("GRIB message lacks a grid definition section")
            if indicator == 0:
                if bitmap is None or len(bitmap) * 8 < points:
                    raise GlofasError("GRIB bitmap is shorter than the number of grid points")
                padding_bits = len(bitmap) * 8 - points
                valid = (int.from_bytes(bitmap, "big") >> padding_bits).bit_count()
                previous_bitmap = bitmap
                digest = hashlib.sha256(bitmap).hexdigest()
                bitmap_hashes.setdefault(digest, {"valid_points": valid, "messages": 0})["messages"] += 1
            elif indicator == 254:
                if previous_bitmap is None:
                    raise GlofasError("GRIB message reuses a bitmap before one is defined")
                padding_bits = len(previous_bitmap) * 8 - points
                valid = (int.from_bytes(previous_bitmap, "big") >> padding_bits).bit_count()
                digest = hashlib.sha256(previous_bitmap).hexdigest()
                bitmap_hashes.setdefault(digest, {"valid_points": valid, "messages": 0})["messages"] += 1
            elif indicator == 255:
                valid = points
                digest = "no-bitmap"
                bitmap_hashes.setdefault(digest, {"valid_points": points, "messages": 0})["messages"] += 1
            else:
                valid, digest = None, f"predefined-{indicator}"
                bitmap_hashes.setdefault(digest, {"valid_points": None, "messages": 0})["messages"] += 1
            records.append({"message": messages + 1, "grid_points": points,
                            "bitmap_indicator": indicator, "valid_grid_points": valid,
                            "bitmap_sha256": digest})
            messages += 1
            stream.seek(message_end)
    return {"message_count": messages, "bitmap_patterns": list(bitmap_hashes.values()),
            "distinct_bitmap_patterns": len(bitmap_hashes), "records": records}


def inspect_glofas(path: Path, include_bitmap_counts: bool = True) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"GloFAS file not found: {path}")
    with path.open("rb") as stream:
        header = stream.read(16)
    if len(header) != 16 or header[:4] != b"GRIB" or header[7] != 2:
        raise GlofasError(f"Not a GRIB2 file: {path}")

    records = []
    with rasterio.open(path) as src:
        if src.driver != "GRIB":
            raise GlofasError(f"GDAL opened {path} as {src.driver}, not GRIB")
        grid = {"width": src.width, "height": src.height, "bands": src.count,
                "crs": src.crs.to_string() if src.crs else None,
                "bounds": [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top],
                "resolution_degrees": [abs(src.transform.a), abs(src.transform.e)],
                "transform": list(src.transform)[:6], "nodata": src.nodata,
                "dtype": src.dtypes[0], "band_block_shape": list(src.block_shapes[0])}
        for band in range(1, src.count + 1):
            tags = src.tags(band)
            namespace_tags = src.tags(band, ns="GRIB")
            ids = tags.get("GRIB_IDS", "")
            match = re.search(r"\bREF_TIME=([^ ]+)", ids)
            ref_text = match.group(1) if match else None
            ref_time = _parse_datetime(ref_text)
            template = int(tags.get("GRIB_PDS_PDTN", -1))
            raw_values = tags.get("GRIB_PDS_TEMPLATE_NUMBERS", "")
            valid_time = _product_valid_time(raw_values, template)
            param_match = re.search(r"GRIB_DISCIPLINE=(\d+)", tags.get("GRIB_DISCIPLINE", ""))
            discipline = int(param_match.group(1)) if param_match else int(header[6])
            raw = [int(value) for value in raw_values.split()]
            category, number = (raw[0], raw[1]) if len(raw) >= 2 else (None, None)
            parameter = PARAMETERS.get((discipline, category, number), {})
            lead_hours = ((valid_time - ref_time).total_seconds() / 3600
                          if valid_time and ref_time else None)
            master_match = re.search(r"MASTER_TABLE=(\d+)", ids)
            type_match = re.search(r"TYPE=([^ ]+)", ids)
            records.append({
                "band": band, "reference_time": ref_time.isoformat() if ref_time else ref_text,
                "valid_time": valid_time.isoformat() if valid_time else None,
                "lead_hours": lead_hours,
                "discipline": discipline, "parameter_category": category,
                "parameter_number": number, "parameter_name": parameter.get("name", "unknown"),
                "parameter_short_name": parameter.get("short_name"),
                "parameter_id": parameter.get("parameter_id"), "unit": parameter.get("unit"),
                "centre": ids.split(" ")[0].split("=")[-1] if ids else None,
                "master_table_version": int(master_match.group(1)) if master_match else None,
                "forecast_or_analysis_type": type_match.group(1) if type_match else None,
                "identification": ids,
                "product_definition_template": template,
                "product_template_description": LOCAL_PRODUCT_TEMPLATES.get(template, "Standard/other GRIB2 product template; raw template retained"),
                "raw_product_template_values": raw,
                "grib_data_representation": namespace_tags,
                "gdal_unit": tags.get("GRIB_UNIT"), "gdal_comment": tags.get("GRIB_COMMENT"),
            })
    signatures = [(r["reference_time"], r["valid_time"], r["discipline"],
                   r["parameter_category"], r["parameter_number"],
                   r["product_definition_template"], tuple(r["raw_product_template_values"])) for r in records]
    duplicates = len(signatures) - len(set(signatures))
    inventory = {
        "path": path.as_posix(), "file_size_bytes": path.stat().st_size,
        "edition": header[7], "discipline": header[6], "grid": grid,
        "variable_summary": sorted({f"{r['parameter_name']} ({r['unit'] or 'unit unknown'})" for r in records}),
        "reference_time_range": [min((r["reference_time"] for r in records if r["reference_time"]), default=None),
                                 max((r["reference_time"] for r in records if r["reference_time"]), default=None)],
        "valid_time_range": [min((r["valid_time"] for r in records if r["valid_time"]), default=None),
                             max((r["valid_time"] for r in records if r["valid_time"]), default=None)],
        "lead_hours": sorted({r["lead_hours"] for r in records if r["lead_hours"] is not None}),
        "product_definition_templates": sorted({r["product_definition_template"] for r in records}),
        "master_table_versions": sorted({r["master_table_version"] for r in records if r["master_table_version"] is not None}),
        "forecast_or_analysis_types": sorted({r["forecast_or_analysis_type"] for r in records if r["forecast_or_analysis_type"]}),
        "duplicate_records": duplicates, "records": records,
        "note": "ECMWF local product template semantics are retained as raw values when GDAL cannot provide named fields. Parameter name/unit use WMO/ECMWF code 1-0-7 mapping.",
    }
    if include_bitmap_counts:
        bitmap_report = _scan_grib_bitmaps(path)
        inventory["bitmap_inventory"] = bitmap_report
        inventory["message_count_matches_raster_bands"] = bitmap_report["message_count"] == grid["bands"]
        valid_counts = {item["valid_points"] for item in bitmap_report["bitmap_patterns"] if item["valid_points"] is not None}
        total_points = grid["width"] * grid["height"]
        if len(valid_counts) == 1 and len(valid_counts) == len(bitmap_report["bitmap_patterns"]):
            inventory["grid_point_count_per_field"] = total_points
            inventory["valid_point_count_per_field"] = next(iter(valid_counts))
            inventory["missing_point_count_per_field"] = total_points - next(iter(valid_counts))
    return inventory


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def nearest_valid_cell(src, latitude: float, longitude: float, reference_band: int,
                       max_distance_km: float = 30.0) -> dict | None:
    if src.crs is None or src.crs.to_epsg() != 4326:
        raise GlofasError("The local discharge query currently requires a WGS84 longitude/latitude grid")
    normalized_lon = ((longitude + 180.0) % 360.0) - 180.0
    row, col = src.index(normalized_lon, latitude)
    row = min(max(0, row), src.height - 1)
    col %= src.width
    radius = max(1, min(20, int(math.ceil(max_distance_km / 5.5))))
    r0, r1 = max(0, row - radius), min(src.height, row + radius + 1)
    c0, c1 = max(0, col - radius), min(src.width, col + radius + 1)
    values = src.read(reference_band, window=Window(c0, r0, c1 - c0, r1 - r0), masked=True)
    candidates = []
    for local_r in range(values.shape[0]):
        for local_c in range(values.shape[1]):
            value = values[local_r, local_c]
            if values.mask[local_r, local_c] or not math.isfinite(float(value)) or float(value) == src.nodata:
                continue
            rr, cc = r0 + local_r, c0 + local_c
            cell_lon, cell_lat = src.xy(rr, cc)
            distance = haversine_km(latitude, longitude, float(cell_lat), float(cell_lon))
            candidates.append((distance, rr, cc, float(cell_lat), float(cell_lon)))
    if not candidates:
        return None
    distance, rr, cc, cell_lat, cell_lon = min(candidates)
    if distance > max_distance_km:
        return {"too_far": True, "distance_km": distance, "row": rr, "column": cc,
                "latitude": cell_lat, "longitude": cell_lon}
    return {"too_far": False, "distance_km": distance, "row": rr, "column": cc,
            "latitude": cell_lat, "longitude": cell_lon}


def extract_discharge_forecasts(src, latitude: float, longitude: float,
                                max_distance_km: float = 30.0) -> tuple[list[dict], dict]:
    """Extract all compatible daily control-forecast records at one nearest river cell."""
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise GlofasError("latitude must be between -90 and 90")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise GlofasError("longitude must be between -180 and 180")
    if latitude < -60 or latitude > 90:
        raise GlofasError("The local GloFAS grid spans latitudes -60 to 90 degrees")
    records = _forecast_records(src)
    if not records:
        raise GlofasError("No compatible ECMWF control-forecast records with decoded valid times were found")
    cell = nearest_valid_cell(src, latitude, longitude, records[0][0], max_distance_km)
    if cell is None:
        raise GlofasError("No valid river-network grid cell was found near this coordinate")
    if cell["too_far"]:
        raise GlofasError(f"Nearest valid river cell is {cell['distance_km']:.2f} km away, beyond limit {max_distance_km:.2f} km")
    from datetime import timedelta
    extracted = []
    for band, reference, valid_time, tags in records:
        raw = src.read(band, window=Window(cell["column"], cell["row"], 1, 1), masked=True)[0, 0]
        value = None if bool(getattr(raw, "mask", False)) or not math.isfinite(float(raw)) or float(raw) == src.nodata else float(raw)
        extracted.append({"record_band": band, "forecast_issued_at": reference.isoformat(),
                          "valid_from": (valid_time - timedelta(hours=24)).isoformat(),
                          "valid_until": valid_time.isoformat(),
                          "forecast_horizon_hours": int((valid_time - reference).total_seconds() / 3600),
                          "river_discharge_m3_s": value, "unit": "m3 s-1",
                          "parameter_code": "discipline=1,category=0,number=7",
                          "product_definition_template": int(tags.get("GRIB_PDS_PDTN", -1)),
                          "record_type": "ECMWF control forecast"})
    return extracted, {"requested_location": {"latitude": latitude, "longitude": longitude},
                       "source_cell": cell, "source": "ECMWF GRIB hydrological discharge field",
                       "grid_resolution_degrees": [abs(src.transform.a), abs(src.transform.e)],
                       "records": len(extracted)}


def _forecast_records(src) -> list:
    raw_records = []
    for band in range(1, src.count + 1):
        tags = src.tags(band)
        ids = tags.get("GRIB_IDS", "")
        if "TYPE=3(Control_forecast)" not in ids:
            continue
        template = int(tags.get("GRIB_PDS_PDTN", -1))
        if template != 73:
            continue
        ref_match = re.search(r"\bREF_TIME=([^ ]+)", ids)
        reference = _parse_datetime(ref_match.group(1)) if ref_match else None
        valid = _product_valid_time(tags.get("GRIB_PDS_TEMPLATE_NUMBERS", ""), template)
        if reference and valid:
            raw_records.append((band, reference, valid, tags))
    return raw_records


def query_discharge_dataset(src, latitude: float, longitude: float,
                            max_distance_km: float = 30.0, records: list | None = None) -> dict:
    """Query a live Rasterio GRIB dataset; values remain external discharge forecasts."""
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise GlofasError("latitude must be between -90 and 90")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise GlofasError("longitude must be between -180 and 180")
    if latitude < -60 or latitude > 90:
        return {"status": "unsupported_location", "coverage_status": "outside_grid_extent",
                "latitude": latitude, "longitude": longitude, "probability": None,
                "reason": "The local GloFAS grid spans latitudes -60 to 90 degrees."}
    raw_records = records if records is not None else _forecast_records(src)
    if not raw_records:
        return {"status": "unavailable", "coverage_status": "no_compatible_forecast_records",
                "latitude": latitude, "longitude": longitude, "probability": None,
                "reason": "No compatible ECMWF control-forecast records with decoded valid times were found."}
    latest_reference = max(item[1] for item in raw_records)
    cycle = sorted((item for item in raw_records if item[1] == latest_reference), key=lambda item: item[2])
    cell = nearest_valid_cell(src, latitude, longitude, cycle[0][0], max_distance_km)
    if cell is None:
        return {"status": "unsupported_location", "coverage_status": "no_valid_river_cell_nearby",
                "latitude": latitude, "longitude": longitude, "probability": None,
                "max_search_distance_km": max_distance_km,
                "reason": "No valid river-network grid cell was found in the configured search window."}
    if cell["too_far"]:
        return {"status": "unsupported_location", "coverage_status": "nearest_cell_too_far",
                "latitude": latitude, "longitude": longitude, "nearest_cell_distance_km": cell["distance_km"],
                "max_search_distance_km": max_distance_km, "probability": None,
                "reason": "The nearest valid river cell is beyond the configured distance limit."}
    forecasts = []
    for band, reference, valid_time, tags in cycle:
        if valid_time <= reference:
            continue
        sample = src.read(band, window=Window(cell["column"], cell["row"], 1, 1), masked=True)[0, 0]
        if bool(getattr(sample, "mask", False)) or not math.isfinite(float(sample)) or float(sample) == src.nodata:
            value = None
        else:
            value = float(sample)
        forecasts.append({"forecast_issued_at": reference.isoformat(), "valid_from": (valid_time - timedelta(hours=24)).isoformat(),
                          "valid_until": valid_time.isoformat(),
                          "forecast_horizon_hours": int((valid_time - reference).total_seconds() / 3600),
                          "river_discharge_m3_s": value,
                          "source": "ECMWF hydrological GRIB parameter 1-0-7 (local GloFAS release unverified)",
                          "product_type": "external hydrological control forecast",
                          "probability": None, "risk_level": None,
                          "product_template": int(tags.get("GRIB_PDS_PDTN", -1))})
    newest_valid = max((item["valid_until"] for item in forecasts if item["valid_until"]), default=None)
    stale = _parse_datetime(newest_valid) < datetime.now(timezone.utc) if newest_valid else True
    return {"status": "stale" if stale else "available", "coverage_status": "river_cell_found_upstream_area_unverified",
            "location": {"latitude": latitude, "longitude": longitude},
            "source_cell": {"latitude": cell["latitude"], "longitude": cell["longitude"],
                            "distance_km": round(cell["distance_km"], 3),
                            "row": cell["row"], "column": cell["column"],
                            "upstream_area_km2": None,
                            "upstream_area_status": "not supplied in local data; cell-to-site hydrological relevance is unverified"},
            "forecast_issued_at": latest_reference.isoformat(),
            "valid_from": min((item["valid_from"] for item in forecasts), default=None),
            "valid_until": newest_valid,
            "available_horizons_hours": sorted({item["forecast_horizon_hours"] for item in forecasts}),
            "forecasts": forecasts, "probability": None, "risk_level": None,
            "source": "ECMWF hydrological GRIB parameter 1-0-7 (local GloFAS release unverified)", "limitations": [
                "This is an externally generated river-discharge forecast, not a flood-event probability.",
                "No local flood-warning threshold or calibrated discharge-to-inundation mapping is available.",
                "The upstream catchment area for this grid cell is unavailable; grid proximity alone does not validate local hydrological relevance.",
                "Local file may be stale; check forecast_issued_at and valid_until before use.",
            ]}


def query_discharge_forecast(path: Path, latitude: float, longitude: float,
                             max_distance_km: float = 30.0) -> dict:
    """Open a GRIB file for one query; long-running servers should reuse a dataset."""
    with rasterio.open(path) as src:
        return query_discharge_dataset(src, latitude, longitude, max_distance_km)


def write_inventory(paths: list[Path], output: Path) -> dict:
    result = {"files": [inspect_glofas(path) for path in paths],
              "parameter_reference": "ECMWF/WMO GRIB2 discipline=1, category=0, number=7 (river/stream discharge; m3 s-1)",
              "product_identity_caveat": "Files are ECMWF hydrological discharge GRIBs consistent with GloFAS content. An explicit GloFAS release/version identifier was not exposed by the locally readable metadata.",
              "glofas_release": None}
    result["compatibility"] = {
        "shared_grid": len({(f["grid"]["width"], f["grid"]["height"], f["grid"]["crs"],
                            tuple(f["grid"]["bounds"])) for f in result["files"]}) == 1,
        "shared_parameter": len({tuple(f["variable_summary"]) for f in result["files"]}) == 1,
        "same_product_definition_templates": len({tuple(f["product_definition_templates"]) for f in result["files"]}) == 1,
        "same_analysis_or_forecast_type": len({tuple(f["forecast_or_analysis_types"]) for f in result["files"]}) == 1,
        "note": "Files with different time ranges/product templates are not concatenated automatically.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
