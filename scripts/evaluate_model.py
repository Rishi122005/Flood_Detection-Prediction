"""Evaluate the saved U-Net on paired Sen1Floods11 labels in a split file."""
from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio

try:
    from .predict_flood import load_model, normalize, predict_array
except ImportError:  # Support direct execution: python scripts/evaluate_model.py
    from predict_flood import load_model, normalize, predict_array


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | int]:
    tp = int(np.sum(y_true & y_pred)); tn = int(np.sum(~y_true & ~y_pred))
    fp = int(np.sum(~y_true & y_pred)); fn = int(np.sum(y_true & ~y_pred))
    div = lambda n, d: float(n / d) if d else 0.0
    precision, recall = div(tp, tp + fp), div(tp, tp + fn)
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "precision": precision, "recall": recall,
            "f1_dice": div(2 * tp, 2 * tp + fp + fn), "iou": div(tp, tp + fp + fn),
            "accuracy": div(tp + tn, tp + tn + fp + fn), "specificity": div(tn, tn + fp)}


def save_scene_figure(image_path: Path, sample_id: str, truth: np.ndarray, valid: np.ndarray,
                      prob: np.ndarray, threshold: float, output_dir: Path) -> Path:
    with rasterio.open(image_path) as src:
        vv = src.read(1).astype(np.float32)
    vv = np.clip((vv + 30) / 30, 0, 1)
    pred = prob >= threshold
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.5), constrained_layout=True)
    fig.suptitle(f"{sample_id} — hand label and U-Net prediction (threshold {threshold:.2f})")
    axes[0].imshow(np.ma.masked_where(~valid, vv), cmap="gray", vmin=0, vmax=1)
    axes[0].set_title("SAR VV")
    axes[1].imshow(np.ma.masked_where(~valid, truth == 1), cmap="Blues", vmin=0, vmax=1)
    axes[1].set_title("Ground truth")
    axes[2].imshow(np.ma.masked_where(~valid, pred), cmap="Oranges", vmin=0, vmax=1)
    axes[2].set_title("Predicted mask")
    axes[3].imshow(np.ma.masked_where(~valid, vv), cmap="gray", vmin=0, vmax=1)
    axes[3].imshow(np.ma.masked_where(~(valid & pred), pred), cmap="autumn", alpha=.55, vmin=0, vmax=1)
    axes[3].set_title("Prediction overlay")
    for ax in axes: ax.axis("off")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{sample_id}_evaluation.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def evaluate(root: Path, split: Path, model_path: Path, out_dir: Path, threshold: float, country: str | None,
             prediction_dir: Path | None = None, sample_id: str | None = None):
    model = None if prediction_dir else load_model(model_path)
    ids = [line.strip() for line in split.read_text().splitlines() if line.strip()]
    country_ids = [item for item in ids if not country or item.casefold().startswith(country.casefold() + "_")]
    if sample_id:
        if sample_id not in ids:
            raise ValueError(f"Requested sample is not listed in split {split}: {sample_id}")
        if country and not sample_id.casefold().startswith(country.casefold() + "_"):
            raise ValueError(f"Requested sample does not match country filter {country}: {sample_id}")
        ids = [sample_id]
    else:
        ids = country_ids
    rows, missing = [], []
    for sample_id in ids:
        if country and not sample_id.casefold().startswith(country.casefold() + "_"):
            continue
        image = root / "data/S1GRDHand" / f"{sample_id}_S1Hand.tif"
        label = root / "data/LabelHand" / f"{sample_id}_LabelHand.tif"
        if not image.is_file() or not label.is_file():
            missing.append(sample_id); continue
        with rasterio.open(image) as src:
            if src.count < 2: raise ValueError(f"Expected VV/VH bands: {image}")
            vv, vh = src.read(1).astype(np.float32), src.read(2).astype(np.float32)
            valid = np.isfinite(vv) & np.isfinite(vh) & (src.read_masks(1) > 0) & (src.read_masks(2) > 0)
            transform, crs, shape = src.transform, src.crs, src.shape
        with rasterio.open(label) as src:
            same_transform = np.allclose(tuple(src.transform), tuple(transform), rtol=0.0, atol=1e-10)
            if src.shape != shape or not same_transform or src.crs != crs:
                raise ValueError(f"Label grid is not aligned with image: {sample_id}")
            truth = src.read(1)
        if not set(np.unique(truth)).issubset({-1, 0, 1}):
            raise ValueError(f"Unexpected label values for {sample_id}: {np.unique(truth)}")
        valid &= truth >= 0
        if not valid.any():
            missing.append(sample_id + " (no valid labeled pixels)"); continue
        cached = prediction_dir / f"{image.stem}_probability.tif" if prediction_dir else None
        if cached and cached.is_file():
            with rasterio.open(cached) as src:
                if src.shape != shape or not np.allclose(tuple(src.transform), tuple(transform), rtol=0, atol=1e-10) or src.crs != crs:
                    raise ValueError(f"Prediction raster grid is not aligned: {cached}")
                prob = src.read(1).astype(np.float32)
                if src.nodata is not None: valid &= prob != src.nodata
        else:
            if model is None:
                missing.append(sample_id + " (prediction raster missing)"); continue
            prob = predict_array(model, normalize(vv, vh, valid))
        if not np.isfinite(prob).all(): raise ValueError(f"Non-finite model output: {sample_id}")
        score = metrics(truth[valid] == 1, prob[valid] >= threshold)
        rows.append({"name": sample_id, "valid_pixels": int(valid.sum()), **score})
        figure_path = save_scene_figure(image, sample_id, truth, valid, prob, threshold, out_dir / "evaluation_figures")
        logging.info("Evaluated %s (%d labeled pixels); figure=%s", sample_id, int(valid.sum()), figure_path)
    if not rows:
        raise RuntimeError("No paired, labeled samples were evaluated")
    # Confusion-count aggregation gives globally pooled pixel metrics.
    pooled = {k: sum(r[k] for r in rows) for k in ("tp", "tn", "fp", "fn")}
    tp, tn, fp, fn = (pooled[k] for k in ("tp", "tn", "fp", "fn"))
    div = lambda n, d: float(n / d) if d else 0.0
    pooled.update(precision=div(tp,tp+fp), recall=div(tp,tp+fn), f1_dice=div(2*tp,2*tp+fp+fn),
                  iou=div(tp,tp+fp+fn), accuracy=div(tp+tn,tp+tn+fp+fn), specificity=div(tn,tn+fp))
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "per_image_metrics.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    macro = {k: float(np.mean([r[k] for r in rows])) for k in ("precision","recall","f1_dice","iou","accuracy","specificity")}
    summary = {"split": str(split), "country_filter": country, "threshold": threshold,
               "scenes_in_country_split": len(country_ids), "scenes_requested": len(ids),
               "images_evaluated": len(rows), "images_skipped": len(missing),
               "missing_or_skipped": missing, "pooled_pixel_metrics": pooled,
               "macro_average_per_scene_metrics": macro}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "summary.md").write_text(
        f"# Evaluation summary\n\n- Split: `{split.name}`\n- Country filter: {country or 'all'}\n- Threshold: {threshold}\n- Scenes in country split: {len(country_ids)}\n- Scenes evaluated: {len(rows)}\n- Scenes skipped: {len(missing)}\n\n"
        "Pooled pixel metrics (micro-averaged):\n\n" + "\n".join(f"- {k}: {v:.4f}" for k,v in pooled.items() if k not in {"tp","tn","fp","fn"}) + "\n\n"
        "Scene metrics (macro-averaged):\n\n" + "\n".join(f"- {k}: {v:.4f}" for k,v in macro.items()) + "\n\n"
        f"Confusion counts: TP={tp}, TN={tn}, FP={fp}, FN={fn}.\n")
    fig, ax = plt.subplots(figsize=(max(8, len(rows) * .8), 5), constrained_layout=True)
    labels = [row["name"].removeprefix("India_") for row in rows]
    x = np.arange(len(rows)); width = .38
    ax.bar(x - width / 2, [r["f1_dice"] for r in rows], width, label="F1 / Dice")
    ax.bar(x + width / 2, [r["iou"] for r in rows], width, label="IoU")
    ax.set(xticks=x, xticklabels=labels, ylim=(0, 1), ylabel="Score", xlabel="Scene ID",
           title=f"Per-scene metrics — {country or 'all scenes'} (threshold {threshold:.2f})")
    ax.tick_params(axis="x", rotation=45); ax.grid(axis="y", alpha=.25); ax.legend()
    fig.savefig(out_dir / "per_scene_metric_comparison.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    return summary


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--split", type=Path, default=root / "splits/flood_test_data.txt")
    p.add_argument("--country", default=None, help="Optional country prefix, for example India")
    p.add_argument("--model", type=Path, default=root / "models/best_unet_flood.keras")
    p.add_argument("--output-dir", type=Path, default=root / "outputs/metrics")
    p.add_argument("--prediction-dir", type=Path, default=None, help="Reuse saved probability GeoTIFFs instead of running inference")
    p.add_argument("--sample-id", default=None, help="Evaluate one ID from the selected split")
    p.add_argument("--threshold", type=float, default=.5)
    a = p.parse_args()
    print(json.dumps(evaluate(root, a.split, a.model, a.output_dir, a.threshold, a.country, a.prediction_dir, a.sample_id), indent=2))


if __name__ == "__main__": main()
