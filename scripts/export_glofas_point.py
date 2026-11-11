#!/usr/bin/env python3
"""Export source-attributed GloFAS discharge forecasts at a coordinate/scene."""

import argparse
import csv
import json
import sys
from pathlib import Path

import rasterio

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecasting.glofas import GlofasError, extract_discharge_forecasts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/glofas/data.grib"))
    locations = parser.add_mutually_exclusive_group(required=True)
    locations.add_argument("--scene", type=Path, help="georeferenced SAR scene; its center is queried")
    locations.add_argument("--coordinates", nargs=2, type=float, metavar=("LAT", "LON"))
    parser.add_argument("--location-id", help="stable location/site identifier for downstream alignment")
    parser.add_argument("--max-distance-km", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=Path("outputs/forecasting/glofas_point_forecast.csv"))
    args = parser.parse_args()
    try:
        if args.scene:
            with rasterio.open(args.scene) as scene:
                if scene.crs is None:
                    raise GlofasError(f"Scene has no CRS: {args.scene}")
                x, y = scene.transform * (scene.width / 2, scene.height / 2)
                if scene.crs.to_epsg() == 4326:
                    lon, lat = x, y
                else:
                    from rasterio.warp import transform
                    lon_values, lat_values = transform(scene.crs, "EPSG:4326", [x], [y])
                    lon, lat = lon_values[0], lat_values[0]
            scene_id = args.scene.stem
        else:
            lat, lon = args.coordinates
            scene_id = None
        with rasterio.open(args.input) as src:
            rows, location = extract_discharge_forecasts(src, lat, lon, args.max_distance_km)
        location_id = args.location_id or scene_id or f"{lat:.5f}_{lon:.5f}"
        for row in rows:
            row["location_id"] = location_id
            row["requested_latitude"] = lat
            row["requested_longitude"] = lon
            row["source_file"] = args.input.as_posix()
            row["source_file_size_bytes"] = args.input.stat().st_size
        args.output.parent.mkdir(parents=True, exist_ok=True)
        fields = ["location_id", "requested_latitude", "requested_longitude", "forecast_issued_at",
                  "valid_from", "valid_until", "forecast_horizon_hours", "river_discharge_m3_s",
                  "unit", "parameter_code", "product_definition_template", "record_type",
                  "source_file", "source_file_size_bytes", "record_band"]
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        location["location_id"] = location_id
        location["source_file"] = args.input.as_posix()
        location["product_scope"] = "external hydrological forecast records; no flood-event labels or probabilities"
        metadata_path = args.output.with_suffix(".json")
        metadata_path.write_text(json.dumps(location, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, rasterio.errors.RasterioError) as exc:
        parser.error(str(exc))
    print(f"Exported {len(rows)} real forecast records to {args.output}")
    print(f"Nearest river cell {location['source_cell']['distance_km']:.3f} km from requested coordinate")
    print(f"Metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
