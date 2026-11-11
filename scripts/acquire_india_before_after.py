"""Acquire a small co-registered Sentinel-1 RTC pair for the India training scene.

The STAC catalog is public; the script signs COG URLs and reads only the
requested window over HTTP. Original project data is never modified.
"""
from __future__ import annotations

import argparse
import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject


CATALOG = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href="
SCENES = {
    "before": "S1A_IW_GRDH_1SDV_20160719T234621_20160719T234650_012224_012FB2_rtc",
    "after": "S1A_IW_GRDH_1SDV_20160812T234622_20160812T234651_012574_013B43_rtc",
}


def get_json(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def acquire(anchor: Path, output_dir: Path) -> dict:
    with rasterio.open(anchor) as reference:
        if reference.count < 2 or reference.crs is None:
            raise ValueError("Anchor must be a georeferenced two-band VV/VH raster")
        shape, transform, crs = (reference.height, reference.width), reference.transform, reference.crs
        bounds_wgs84 = rasterio.warp.transform_bounds(crs, "EPSG:4326", *reference.bounds)
    query = {"collections": ["sentinel-1-rtc"], "bbox": list(bounds_wgs84),
             "datetime": "2016-07-18T00:00:00Z/2016-08-13T23:59:59Z", "limit": 100}
    features = get_json(CATALOG, query).get("features", [])
    items = {item["id"]: item for item in features}
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {"anchor": str(anchor), "anchor_crs": str(crs), "anchor_shape": list(shape),
              "pair": {}, "classification_caveat": "RTC VV/VH inputs are compatible in polarization and orbit; RTC processing differs from the Sen1Floods11 training product, so these are exploratory model outputs, not validated flood labels."}
    for label, item_id in SCENES.items():
        item = items.get(item_id)
        if item is None:
            raise RuntimeError(f"Expected same-footprint catalog item missing: {item_id}")
        props = item["properties"]
        pols = set(props.get("sar:polarizations", []))
        if not {"VV", "VH"}.issubset(pols) or props.get("sat:relative_orbit") != 77 or props.get("sat:orbit_state") != "descending":
            raise ValueError(f"Incompatible acquisition metadata for {item_id}")
        assets = item.get("assets", {})
        for band in ("vv", "vh"):
            if band not in assets:
                raise ValueError(f"Missing {band} RTC asset for {item_id}")
        target = np.full((2, *shape), np.nan, dtype=np.float32)
        valid_band = np.ones(shape, dtype=bool)
        for index, band in enumerate(("vv", "vh")):
            href = assets[band]["href"]
            signed = get_json(SIGN + urllib.parse.quote(href, safe=""))["href"]
            # Rasterio/GDAL reads the signed Cloud Optimized GeoTIFF by HTTP range.
            with rasterio.open(signed) as source:
                source_values = np.full(shape, np.nan, dtype=np.float32)
                reproject(source=rasterio.band(source, 1), destination=source_values,
                          src_transform=source.transform, src_crs=source.crs, src_nodata=source.nodata,
                          dst_transform=transform, dst_crs=crs, dst_nodata=np.nan,
                          resampling=Resampling.bilinear, num_threads=2)
                # The RTC assets store linear gamma-nought power; this U-Net
                # was trained on dB, so convert 10*log10 before its existing
                # VV/VH-specific clipping and normalization.
                positive = np.isfinite(source_values) & (source_values > 0)
                target[index] = np.where(positive, 10.0 * np.log10(source_values), np.nan)
                valid_band &= positive
                if index == 0:
                    source_info = {"crs": str(source.crs), "resolution": list(source.res),
                                   "shape": [source.height, source.width], "nodata": source.nodata}
        valid_pct = float(valid_band.mean() * 100)
        if valid_pct < 90:
            raise RuntimeError(f"Only {valid_pct:.1f}% of the anchor grid is covered in {label}; refusing to make an incomplete pair")
        path = output_dir / f"{label}_{props['datetime'][:10]}_VV_VH.tif"
        profile = {"driver": "GTiff", "height": shape[0], "width": shape[1], "count": 2,
                   "dtype": "float32", "crs": crs, "transform": transform, "nodata": -9999.0,
                   "compress": "deflate", "predictor": 3}
        with rasterio.open(path, "w", **profile) as dest:
            for band_index in (0, 1):
                dest.write(np.where(valid_band, target[band_index], -9999.0), band_index + 1)
            dest.update_tags(acquisition_time=props["datetime"], source_item=item_id,
                             sensor="Sentinel-1 RTC", polarizations="VV,VH",
                             backscatter_units="dB (converted from linear RTC gamma0)",
                             relative_orbit=str(props["sat:relative_orbit"]), orbit_state=props["sat:orbit_state"])
        result["pair"][label] = {"item_id": item_id, "acquisition_time": props["datetime"],
                                 "relative_orbit": props["sat:relative_orbit"], "orbit_state": props["sat:orbit_state"],
                                 "polarizations": sorted(pols), "valid_coverage_percent": valid_pct,
                                 "source_raster": source_info, "output": str(path)}
        logging.info("Wrote %s date %s with %.2f%% grid coverage: %s", label, props["datetime"], valid_pct, path)
    report = output_dir / "pair_metadata.json"
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--anchor", type=Path, default=root / "data/S1GRDHand/India_1017769_S1Hand.tif")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs/before_after_India_1017769")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print(json.dumps(acquire(args.anchor, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
