"""Run tiled Sentinel-1 VV/VH flood inference with the saved U-Net."""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import rasterio
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "2")

tf = None
TFLITE_INTERPRETER = None
if os.environ.get("FLOOD_TFLITE_RUNTIME_ONLY") == "1":
    try:
        from ai_edge_litert.interpreter import Interpreter as TFLITE_INTERPRETER
    except ImportError:
        try:
            from tflite_runtime.interpreter import Interpreter as TFLITE_INTERPRETER
        except ImportError as exc:
            raise RuntimeError(
                "FLOOD_TFLITE_RUNTIME_ONLY=1 requires ai-edge-litert or tflite-runtime"
            ) from exc
else:
    import tensorflow as tf
    TFLITE_INTERPRETER = tf.lite.Interpreter

try:
    if tf is not None:
        tf.config.threading.set_intra_op_parallelism_threads(int(os.environ["TF_NUM_INTRAOP_THREADS"]))
        tf.config.threading.set_inter_op_parallelism_threads(int(os.environ["TF_NUM_INTEROP_THREADS"]))
except RuntimeError:
    # A host application may have initialized TensorFlow before importing this module.
    pass

LOGGER = logging.getLogger("flood_prediction")


class TFLitePredictor:
    """Float32 TFLite adapter; preserves the saved Keras model's tensor contract."""
    def __init__(self, model_path: Path, threads: int = 8):
        if TFLITE_INTERPRETER is None:
            raise RuntimeError("No TensorFlow Lite interpreter is available")
        self.interpreter = TFLITE_INTERPRETER(model_path=str(model_path), num_threads=threads)
        self.interpreter.allocate_tensors()
        input_detail = self.interpreter.get_input_details()[0]
        output_detail = self.interpreter.get_output_details()[0]
        self.input_index = input_detail["index"]
        self.output_index = output_detail["index"]
        self.input_shape = tuple(input_detail["shape"])
        self.output_shape = tuple(output_detail["shape"])
        self._input_dtype = input_detail["dtype"]

    def predict(self, batch, verbose=0):
        self.interpreter.set_tensor(self.input_index, np.asarray(batch, dtype=self._input_dtype))
        self.interpreter.invoke()
        return self.interpreter.get_tensor(self.output_index)


def load_tflite_model(checkpoint: Path, cache_path: Path, threads: int = 8):
    """Convert checkpoint once to float32 TFLite, then use its optimized CPU kernels."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    stage_start = time.perf_counter()
    if not cache_path.is_file():
        if tf is None:
            raise FileNotFoundError(
                f"Preconverted TensorFlow Lite model not found: {cache_path}; "
                "the TFLite-only deployment cannot convert a Keras checkpoint at runtime"
            )
        model = load_model(checkpoint)
        LOGGER.info("Converting saved float32 checkpoint to TFLite CPU artifact")
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS]
        converted = converter.convert()
        temp_path = cache_path.with_suffix(".tflite.tmp")
        temp_path.write_bytes(converted)
        temp_path.replace(cache_path)
        LOGGER.info("TFLite conversion completed in %.3fs (%d bytes)", time.perf_counter() - stage_start,
                    cache_path.stat().st_size)
        del model, converter, converted
        gc.collect()
    predictor = TFLitePredictor(cache_path, threads=threads)
    LOGGER.info("Loaded TFLite model (input=%s output=%s threads=%d)",
                predictor.input_shape, predictor.output_shape, threads)
    return predictor, time.perf_counter() - stage_start


def load_model(path: Path):
    if tf is None:
        raise RuntimeError("Keras checkpoint loading is unavailable in TFLite-only mode")
    if not path.is_file():
        raise FileNotFoundError(f"Model not found: {path}")
    try:
        model = tf.keras.models.load_model(path, compile=False)
    except Exception as exc:
        raise RuntimeError(f"Could not load Keras model '{path}': {exc}") from exc
    LOGGER.info("Loaded model %s (input=%s, output=%s)", path, model.input_shape, model.output_shape)
    LOGGER.info("Keras trainable/nontrainable parameter count=%d", model.count_params())
    devices = tf.config.list_physical_devices("GPU")
    LOGGER.info("TensorFlow device: %s", ", ".join(device.name for device in devices) if devices else "CPU")
    return model


def discover_india_scenes(data_dir: Path) -> list[Path]:
    """Find compatible India SAR rasters from filenames, case-insensitively."""
    image_dir = data_dir / "S1GRDHand"
    if not image_dir.is_dir():
        raise FileNotFoundError(f"SAR image directory not found: {image_dir}")
    india_token = re.compile(r"(?:^|[_.-])india(?:[_.-]|$)", re.IGNORECASE)
    scenes = []
    for path in sorted(p for p in image_dir.rglob("*") if p.is_file() and p.suffix.casefold() in {".tif", ".tiff"}):
        if not india_token.search(path.stem):
            continue
        try:
            with rasterio.open(path) as src:
                if src.count < 2 or src.width < 1 or src.height < 1:
                    LOGGER.warning("Skipping incompatible India raster (need two bands): %s", path)
                    continue
                desc = [d.strip().upper() if d else "" for d in src.descriptions[:2]]
                if any(desc) and not (desc[0].startswith("VV") and desc[1].startswith("VH")):
                    LOGGER.warning("Skipping India raster with unexpected band descriptions %s: %s", desc, path)
                    continue
        except rasterio.errors.RasterioError as exc:
            LOGGER.warning("Skipping unreadable India raster %s: %s", path, exc)
            continue
        scenes.append(path)
    return scenes


def normalize(vv: np.ndarray, vh: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Match notebook preprocessing: VV [-30, 0] dB, VH [-35, -5] dB."""
    vv_n = np.clip((vv + 30.0) / 30.0, 0.0, 1.0)
    vh_n = np.clip((vh + 35.0) / 30.0, 0.0, 1.0)
    return np.stack((np.where(valid, vv_n, 0), np.where(valid, vh_n, 0)), axis=-1).astype(np.float32)


def tile_starts(length: int, tile: int, stride: int) -> list[int]:
    if length <= tile:
        return [0]
    starts = list(range(0, length - tile + 1, stride))
    if starts[-1] != length - tile:
        starts.append(length - tile)
    return starts


def predict_array(model, image: np.ndarray, tile: int = 512, overlap: int = 64) -> np.ndarray:
    h, w, _ = image.shape
    if tile < 1 or overlap < 0 or overlap >= tile:
        raise ValueError("tile must be positive and overlap must be in [0, tile)")
    stride = tile - overlap
    if stride <= 0:
        raise ValueError("overlap must be smaller than tile size")
    ys, xs = tile_starts(h, tile, stride), tile_starts(w, tile, stride)
    direct_predict = tf is not None and isinstance(model, tf.keras.Model)
    total = np.zeros((h, w), dtype=np.float64)
    weights = np.zeros((h, w), dtype=np.float32)
    for y in ys:
        for x in xs:
            crop = image[y:min(y + tile, h), x:min(x + tile, w)]
            ch, cw = crop.shape[:2]
            if ch < tile or cw < tile:
                pad = ((0, tile - ch), (0, tile - cw), (0, 0))
                crop = np.pad(crop, pad, mode="reflect" if min(ch, cw) > 1 else "edge")
            tile_start = time.perf_counter()
            if direct_predict:
                # Eager Keras execution avoids the expensive whole-network Grappler
                # trace/optimization observed on native Windows CPU for this model.
                pred = np.asarray(model(tf.convert_to_tensor(crop[None, ...]), training=False).numpy())[0, ..., 0]
            else:
                pred = np.asarray(model.predict(crop[None, ...], verbose=0))[0, ..., 0]
            LOGGER.info("Inference tile x=%d y=%d (%dx%d) completed in %.3fs", x, y, cw, ch,
                        time.perf_counter() - tile_start)
            if pred.shape != (tile, tile):
                raise ValueError(f"Model returned unexpected tile shape: {pred.shape}")
            total[y:y + ch, x:x + cw] += pred[:ch, :cw]
            weights[y:y + ch, x:x + cw] += 1
    return (total / np.maximum(weights, 1))[...,].astype(np.float32)


def pixel_area_m2(transform, crs, height: int, width: int) -> np.ndarray | None:
    """Per-row pixel area; equal-area reprojection for geographic, affine for projected grids."""
    if crs is None:
        return None
    if crs.is_projected:
        try:
            _, factor = crs.linear_units_factor
        except (AttributeError, ValueError):
            return None
        if factor is None:
            return None
        return np.full(height, abs(transform.a * transform.e - transform.b * transform.d) * factor**2)
    if crs.is_geographic:
        try:
            from rasterio.warp import transform as reproject_coordinates
            # Coordinates are transformed into a global equal-area CRS. Process
            # two scanline edges at a time so large rasters do not need a full
            # vertex mesh in memory.
            areas = np.zeros(height, dtype=np.float64)
            col_edges = np.arange(width + 1, dtype=np.float64)
            for row in range(height):
                top = [transform @ (col, row) for col in col_edges]
                bottom = [transform @ (col, row + 1) for col in col_edges]
                xx = [point[0] for point in top] + [point[0] for point in bottom]
                yy = [point[1] for point in top] + [point[1] for point in bottom]
                tx, ty = reproject_coordinates(crs, "EPSG:6933", xx, yy)
                xt, xb = np.asarray(tx[:width + 1]), np.asarray(tx[width + 1:])
                yt, yb = np.asarray(ty[:width + 1]), np.asarray(ty[width + 1:])
                # Shoelace area for every cell in this row.
                areas[row] = np.sum(np.abs(xt[:-1] * yt[1:] + xt[1:] * yb[1:] + xb[1:] * yb[:-1] + xb[:-1] * yt[:-1]
                                             - yt[:-1] * xt[1:] - yt[1:] * xb[1:] - yb[1:] * xb[:-1] - yb[:-1] * xt[:-1]) / 2)
            # Return scalar area per row for north-up grids and per-row average
            # when rotated. Current Sen1Floods11 grids are north-up.
            return areas / width
        except Exception:
            return None
    return None


def cached_prediction(input_path: Path, output_dir: Path) -> dict | None:
    """Return a prior result only if the mask and probability rasters still match the source grid."""
    stem = input_path.stem
    probability_path = output_dir / f"{stem}_probability.tif"
    mask_path = output_dir / f"{stem}_mask.tif"
    summary_path = output_dir / f"{stem}_summary.json"
    if not all(path.is_file() for path in (probability_path, mask_path, summary_path)):
        return None
    try:
        with rasterio.open(input_path) as source, rasterio.open(probability_path) as prob, rasterio.open(mask_path) as mask:
            aligned = (source.shape == prob.shape == mask.shape
                       and source.crs == prob.crs == mask.crs
                       and np.allclose(tuple(source.transform), tuple(prob.transform), rtol=0, atol=1e-10)
                       and np.allclose(tuple(source.transform), tuple(mask.transform), rtol=0, atol=1e-10))
            if not aligned:
                return None
            p, m = prob.read(1), mask.read(1)
            source_valid = np.isfinite(source.read(1)) & np.isfinite(source.read(2))
            source_valid &= (source.read_masks(1) > 0) & (source.read_masks(2) > 0)
            if source.nodata is not None and np.isfinite(source.nodata):
                source_valid &= (source.read(1) != source.nodata) & (source.read(2) != source.nodata)
            pvalid = np.isfinite(p) & ((p != prob.nodata) if prob.nodata is not None else True)
            mvalid = m != mask.nodata if mask.nodata is not None else np.ones(m.shape, bool)
            if not pvalid.any() or not mvalid.any() or not np.isfinite(p[pvalid]).all():
                return None
            if not np.array_equal(pvalid, source_valid) or not np.array_equal(mvalid, source_valid):
                return None
            if p[pvalid].min() < 0 or p[pvalid].max() > 1 or not set(np.unique(m[mvalid])).issubset({0, 1}):
                return None
        with summary_path.open() as f:
            summary = json.load(f)
        if summary.get("height") != mask.shape[0] or summary.get("width") != mask.shape[1]:
            return None
        if int(summary.get("valid_pixels", -1)) != int(source_valid.sum()):
            return None
        threshold = float(summary.get("threshold", .5))
        if not np.array_equal(m[source_valid], (p[source_valid] >= threshold).astype(m.dtype)):
            return None
        return summary
    except (OSError, ValueError, rasterio.errors.RasterioError, json.JSONDecodeError):
        return None


def _upsert_predictions_csv(output_dir: Path, record: dict) -> None:
    csv_path = output_dir / "predictions.csv"
    previous = []
    if csv_path.is_file():
        with csv_path.open(newline="") as f:
            previous = [row for row in csv.DictReader(f) if Path(row.get("input", "")).stem != Path(record["input"]).stem]
    temp_path = csv_path.with_suffix(".csv.tmp")
    with temp_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=record.keys()); writer.writeheader(); writer.writerows(previous); writer.writerow(record)
    temp_path.replace(csv_path)


def run(input_path: Path, model_path: Path, output_dir: Path, threshold: float, tile: int, overlap: int,
        model=None, model_load_seconds: float | None = None):
    started = time.perf_counter()
    timings = {}
    if not input_path.is_file():
        raise FileNotFoundError(f"Input SAR image not found: {input_path}")
    if model is None:
        stage_start = time.perf_counter()
        model = load_model(model_path)
        timings["model_load_seconds"] = time.perf_counter() - stage_start
    elif model_load_seconds is not None:
        timings["model_load_seconds"] = model_load_seconds
    shape = tuple(model.input_shape[1:])
    if len(shape) != 3 or shape[-1] != 2:
        raise ValueError(f"Expected model input HxWx2, got {model.input_shape}")
    if shape[0] is not None and shape[1] is not None and shape[0] != shape[1]:
        raise ValueError(f"Only square model tiles are supported, got {shape[:2]}")
    tile = int(shape[0]) if shape[0] is not None else tile
    stage_start = time.perf_counter()
    LOGGER.info("Reading Sentinel-1 raster: %s", input_path)
    with rasterio.open(input_path) as src:
        if src.count < 2:
            raise ValueError(f"Expected two bands (VV, VH), found {src.count}: {input_path}")
        desc = [d.strip().upper() if d else "" for d in src.descriptions[:2]]
        if any(desc) and not (desc[0].startswith("VV") and desc[1].startswith("VH")):
            raise ValueError(f"Expected bands in VV, VH order; found {desc}: {input_path}")
        vv, vh = src.read(1).astype(np.float32), src.read(2).astype(np.float32)
        valid = np.isfinite(vv) & np.isfinite(vh)
        for band in (1, 2):
            valid &= src.read_masks(band) > 0
        if src.nodata is not None and np.isfinite(src.nodata):
            valid &= (vv != src.nodata) & (vh != src.nodata)
        meta, transform, crs = src.profile.copy(), src.transform, src.crs
    timings["raster_read_seconds"] = time.perf_counter() - stage_start
    if not valid.any():
        raise ValueError(f"No valid VV/VH pixels in {input_path}")
    stage_start = time.perf_counter()
    image = normalize(vv, vh, valid)
    timings["preprocess_seconds"] = time.perf_counter() - stage_start
    LOGGER.info("Normalized %s to %s; valid pixels=%d/%d", input_path.name, image.shape,
                int(valid.sum()), int(valid.size))
    stage_start = time.perf_counter()
    LOGGER.info("Starting model inference (tile=%d, overlap=%d)", tile, min(overlap, tile - 1))
    prob = predict_array(model, image, tile=tile, overlap=min(overlap, tile - 1))
    timings["inference_seconds"] = time.perf_counter() - stage_start
    LOGGER.info("Model inference finished in %.3fs", timings["inference_seconds"])
    if not np.isfinite(prob).all():
        raise ValueError("Model returned NaN or infinite probabilities")
    prob = np.clip(prob, 0, 1)
    mask = (prob >= threshold).astype(np.uint8)
    flood_px, valid_px = int((mask & valid).sum()), int(valid.sum())
    stage_start = time.perf_counter()
    row_area = pixel_area_m2(transform, crs, vv.shape[0], vv.shape[1])
    if row_area is None:
        total_area = flood_area = None
    else:
        pixel_areas = np.broadcast_to(row_area[:, None], valid.shape)
        total_area = float(pixel_areas[valid].sum())
        flood_area = float(pixel_areas[valid & (mask == 1)].sum())
    timings["area_calculation_seconds"] = time.perf_counter() - stage_start

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    profile = meta.copy()
    profile.pop("blockxsize", None)
    profile.pop("blockysize", None)
    profile.update(driver="GTiff", count=1, compress="deflate", tiled=True,
                   blockxsize=256, blockysize=256, dtype="float32", nodata=-9999.0)
    stage_start = time.perf_counter()
    prob_out = np.asarray(prob, dtype=np.float32)
    prob_out[~valid] = -9999
    with rasterio.open(output_dir / f"{stem}_probability.tif", "w", **profile) as dst:
        dst.write(prob_out, 1)
    profile.update(dtype="uint8", nodata=255)
    with rasterio.open(output_dir / f"{stem}_mask.tif", "w", **profile) as dst:
        mask_out = np.asarray(mask, dtype=np.uint8)
        mask_out[~valid] = 255
        dst.write(mask_out, 1)
    timings["raster_write_seconds"] = time.perf_counter() - stage_start

    stage_start = time.perf_counter()
    vv_show = np.clip((vv + 30) / 30, 0, 1)
    vh_show = np.clip((vh + 35) / 30, 0, 1)
    fig, axes = plt.subplots(1, 4, figsize=(18, 5), constrained_layout=True)
    fig.suptitle(f"Sen1Floods11 India sample: {input_path.name}\nU-Net prediction (threshold {threshold:.2f})")
    axes[0].imshow(np.ma.masked_where(~valid, vv_show), cmap="gray", vmin=0, vmax=1); axes[0].set_title("VV input")
    axes[1].imshow(np.ma.masked_where(~valid, vh_show), cmap="gray", vmin=0, vmax=1); axes[1].set_title("VH input")
    im = axes[2].imshow(np.ma.masked_where(~valid, prob), cmap="magma", vmin=0, vmax=1); axes[2].set_title("Flood probability")
    fig.colorbar(im, ax=axes[2], fraction=.046, label="Probability")
    axes[3].imshow(np.ma.masked_where(~valid, vv_show), cmap="gray", vmin=0, vmax=1)
    axes[3].imshow(np.ma.masked_where(~(valid & (mask == 1)), mask), cmap="autumn", alpha=.55, vmin=0, vmax=1)
    axes[3].set_title("Predicted flood overlay")
    fig.legend(handles=[Patch(facecolor="orangered", alpha=.55, label="Predicted flood")], loc="lower right")
    for ax in axes: ax.axis("off")
    fig.savefig(output_dir / f"{stem}_prediction.png", dpi=220, bbox_inches="tight")
    plt.close(fig)
    timings["overlay_seconds"] = time.perf_counter() - stage_start
    record = {
        "input": str(input_path), "model": str(model_path), "threshold": threshold,
        "height": int(vv.shape[0]), "width": int(vv.shape[1]), "valid_pixels": valid_px,
        "predicted_flood_pixels": flood_px, "predicted_flood_percent_valid": 100 * flood_px / valid_px,
        "crs": str(crs) if crs else None,
        "total_valid_area_km2": total_area / 1e6 if total_area is not None else None,
        "predicted_flood_area_km2": flood_area / 1e6 if flood_area is not None else None,
        "area_method": "pixel footprints transformed to equal-area EPSG:6933" if crs and crs.is_geographic and total_area is not None else ("affine pixel area with CRS unit conversion" if total_area is not None else "unavailable"),
        "timings": timings,
    }
    stage_start = time.perf_counter()
    with (output_dir / f"{stem}_summary.json").open("w") as f: json.dump(record, f, indent=2)
    _upsert_predictions_csv(output_dir, record)
    timings["summary_seconds"] = time.perf_counter() - stage_start
    timings["total_seconds"] = time.perf_counter() - started
    with (output_dir / f"{stem}_summary.json").open("w") as f:
        json.dump(record, f, indent=2)
    _upsert_predictions_csv(output_dir, record)
    LOGGER.info("Completed %s in %.3fs; %d/%d flood-label pixels (%.2f%%)", input_path.name,
                timings["total_seconds"], flood_px, valid_px, record["predicted_flood_percent_valid"])
    return record


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, nargs="?", help="Two-band GeoTIFF (band 1 VV, band 2 VH)")
    parser.add_argument("--discover-india", action="store_true", help="Discover India SAR scenes under data/S1GRDHand")
    parser.add_argument("--max-images", type=int, default=1, help="Discovery limit (default: 1; use 0 for all scenes)")
    parser.add_argument("--model", type=Path, default=root / "models/best_unet_flood.keras")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs/predictions")
    parser.add_argument("--threshold", type=float, default=.5)
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=64)
    parser.add_argument("--runtime", choices=("keras", "tflite"), default="tflite",
                        help="Inference engine; TFLite float32 uses optimized CPU kernels and the same checkpoint weights")
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1: parser.error("--threshold must be between 0 and 1")
    if args.discover_india:
        if args.image: parser.error("Do not combine IMAGE with --discover-india")
        if args.max_images < 0: parser.error("--max-images must be non-negative")
        scenes = discover_india_scenes(root / "data")
        if not scenes: parser.error("No compatible India SAR GeoTIFFs were found under data/S1GRDHand")
        discovered_count = len(scenes)
        selected = scenes if args.max_images == 0 else scenes[:args.max_images]
        LOGGER.info("Discovered %d compatible India scenes; processing %d", len(scenes), len(selected))
    else:
        if not args.image: parser.error("Provide IMAGE or pass --discover-india")
        discovered_count = 1
        selected = [args.image]
    if args.discover_india:
        status_path = args.output_dir / "scene_processing_status.csv"
        statuses = []
        def save_statuses():
            args.output_dir.mkdir(parents=True, exist_ok=True)
            temp = status_path.with_suffix(".csv.tmp")
            with temp.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=("scene", "status", "reason")); writer.writeheader(); writer.writerows(statuses)
            temp.replace(status_path)
    model = None
    model_error = None
    model_load_seconds = None
    processed = reused = skipped = 0
    for index, scene in enumerate(selected, 1):
        LOGGER.info("Scene %d/%d: %s", index, len(selected), scene.name)
        try:
            record = cached_prediction(scene, args.output_dir) if args.discover_india else None
            if record is not None:
                reused += 1
                _upsert_predictions_csv(args.output_dir, record)
                status = {"scene": scene.name, "status": "reused", "reason": "validated cached rasters"}
            else:
                if model is None:
                    if model_error is not None:
                        raise RuntimeError(f"Model loading previously failed: {model_error}")
                    try:
                        load_started = time.perf_counter()
                        if args.runtime == "tflite":
                            digest = hashlib.sha256()
                            with args.model.open("rb") as checkpoint_file:
                                for block in iter(lambda: checkpoint_file.read(1024 * 1024), b""):
                                    digest.update(block)
                            checkpoint_hash = digest.hexdigest()[:12]
                            cache = root / "outputs/model_cache" / f"best_unet_flood_{checkpoint_hash}.tflite"
                            model, model_load_seconds = load_tflite_model(args.model, cache, threads=8)
                        else:
                            model = load_model(args.model)
                            model_load_seconds = time.perf_counter() - load_started
                        LOGGER.info("Model/runtime initialization completed in %.3fs", model_load_seconds)
                    except Exception as exc:
                        model_error = exc
                        raise RuntimeError(str(exc)) from exc
                record = run(scene, args.model, args.output_dir, args.threshold, args.tile_size,
                             args.overlap, model=model, model_load_seconds=model_load_seconds)
                processed += 1
                status = {"scene": scene.name, "status": "processed", "reason": ""}
            print(json.dumps(record, indent=2), flush=True)
            if args.discover_india:
                statuses.append(status); save_statuses()
        except Exception as exc:
            LOGGER.error("Failed to process %s: %s", scene, exc)
            skipped += 1
            if args.discover_india:
                statuses.append({"scene": scene.name, "status": "skipped", "reason": str(exc)}); save_statuses()
            else:
                raise SystemExit(2) from exc
    if args.discover_india:
        LOGGER.info("Finished: discovered=%d processed=%d reused=%d skipped=%d; status=%s",
                    discovered_count, processed, reused, skipped, status_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
