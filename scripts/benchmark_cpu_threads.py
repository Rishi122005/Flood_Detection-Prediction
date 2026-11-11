"""Benchmark float32 TFLite inference on one real scene at several CPU thread counts."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.predict_flood import TFLitePredictor, normalize


def main() -> int:
    root = ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, default=root / "data/S1GRDHand/India_1017769_S1Hand.tif", nargs="?")
    parser.add_argument("--model", type=Path, required=True, help="Cached float32 TFLite model derived from the checkpoint")
    parser.add_argument("--threads", type=int, nargs="+", default=[1, 2, 4, 8])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    started = time.perf_counter()
    with rasterio.open(args.image) as src:
        if src.count < 2 or src.descriptions[:2] != ("VV", "VH"):
            raise ValueError("Benchmark input must be VV then VH Sentinel-1 GeoTIFF")
        vv, vh = src.read(1).astype(np.float32), src.read(2).astype(np.float32)
        valid = np.isfinite(vv) & np.isfinite(vh) & (src.read_masks(1) > 0) & (src.read_masks(2) > 0)
    batch = normalize(vv, vh, valid)[None, ...]
    reference = None
    for count in args.threads:
        predictor = TFLitePredictor(args.model, threads=count)
        begin = time.perf_counter()
        prediction = predictor.predict(batch)[0, ..., 0]
        elapsed = time.perf_counter() - begin
        if reference is None:
            reference = prediction.copy()
            difference = 0.0
        else:
            difference = float(np.max(np.abs(prediction - reference)))
        print({"threads": count, "inference_seconds": round(elapsed, 4),
               "max_abs_difference_from_first": difference}, flush=True)
        del predictor
    print({"total_seconds": round(time.perf_counter() - started, 4)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
