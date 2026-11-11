"""Create a co-registered change raster and report for a processed SAR pair."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.patches import Patch
try:
    from .predict_flood import pixel_area_m2
except ImportError:
    from predict_flood import pixel_area_m2

def compare(root: Path) -> dict:
    before_name = "before_2016-07-19_VV_VH"
    after_name = "after_2016-08-12_VV_VH"
    paths = {
        "before_input": root / (before_name + ".tif"), "after_input": root / (after_name + ".tif"),
        "before_prediction": root / "predictions/before" / (before_name + "_prediction.png"),
        "after_prediction": root / "predictions/after" / (after_name + "_prediction.png"),
        "before_mask": root / "predictions/before" / (before_name + "_mask.tif"),
        "after_mask": root / "predictions/after" / (after_name + "_mask.tif"),
        "before_probability": root / "predictions/before" / (before_name + "_probability.tif"),
        "after_probability": root / "predictions/after" / (after_name + "_probability.tif"),
    }
    with rasterio.open(paths["before_mask"]) as b, rasterio.open(paths["after_mask"]) as a:
        if (b.shape, b.crs, b.transform) != (a.shape, a.crs, a.transform):
            raise ValueError("Pair predictions are not exactly grid aligned")
        bm, am = b.read(1), a.read(1)
        valid = (bm != 255) & (am != 255)
        meta, transform, crs = b.profile.copy(), b.transform, b.crs
    before, after_mask = (bm == 1) & valid, (am == 1) & valid
    newly, receded, persistent = after_mask & ~before, before & ~after_mask, before & after_mask
    change = np.zeros(valid.shape, dtype=np.uint8)
    change[newly], change[receded], change[persistent] = 1, 2, 3
    change[~valid] = 255
    change_path = root / "change_mask.tif"
    meta.update(count=1, dtype="uint8", nodata=255, compress="deflate")
    with rasterio.open(change_path, "w", **meta) as dest:
        dest.write(change, 1)
        dest.update_tags(class_1="newly_segmented_water", class_2="receded_segmented_water",
                         class_3="persistent_segmented_water", nodata="invalid")
    areas = pixel_area_m2(transform, crs, valid.shape[0], valid.shape[1])
    weights = np.broadcast_to(areas[:, None], valid.shape)
    total_area = float(weights[valid].sum())
    area = lambda mask: float(weights[mask].sum())
    report = {
        "before_date": "2016-07-19T23:46:35.531671Z", "after_date": "2016-08-12T23:46:36.825740Z",
        "days_between": 24, "grid_aligned": True, "crs": str(crs), "shape": list(valid.shape),
        "valid_pixels": int(valid.sum()), "total_valid_area_km2": total_area / 1e6,
        "before_segmented_pixels": int(before.sum()), "after_segmented_pixels": int(after_mask.sum()),
        "newly_segmented_pixels": int(newly.sum()), "receded_segmented_pixels": int(receded.sum()),
        "persistent_segmented_pixels": int(persistent.sum()),
        "before_segmented_percent": float(before.sum() / valid.sum() * 100),
        "after_segmented_percent": float(after_mask.sum() / valid.sum() * 100),
        "change_percentage_points": float((after_mask.sum() - before.sum()) / valid.sum() * 100),
        "before_segmented_area_km2": area(before) / 1e6, "after_segmented_area_km2": area(after_mask) / 1e6,
        "newly_segmented_area_km2": area(newly) / 1e6, "receded_segmented_area_km2": area(receded) / 1e6,
        "change_raster": str(change_path), "artifacts": {k: str(v) for k, v in paths.items()},
        "interpretation": "Exploratory U-Net change on a same-orbit, co-registered RTC pair; zero detections do not establish absence of flooding. Seasonal water, calibration differences, and model domain shift are not independently resolved."
    }
    with rasterio.open(paths["before_input"]) as b, rasterio.open(paths["after_input"]) as a:
        bv, av = b.read(1), a.read(1)
    bv_db, av_db = bv, av
    bv, av = np.clip((bv_db + 30) / 30, 0, 1), np.clip((av_db + 30) / 30, 0, 1)
    colors = np.zeros((*change.shape, 4), dtype=np.float32)
    colors[newly], colors[receded], colors[persistent] = (1.0,.15,.10,.85), (.15,.55,1.0,.85), (.95,.78,.1,.65)
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    for ax, img, title in zip(axes[0], (bv, av, np.abs(av_db-bv_db)),
          ("Before VV · 2016-07-19", "After VV · 2016-08-12", "Absolute VV difference (dB)")):
        ax.imshow(img, cmap="gray" if title.startswith(("Before", "After")) else "magma",
                  vmin=0 if title.startswith("Absolute") else None,
                  vmax=15 if title.startswith("Absolute") else None)
        ax.set_title(title); ax.axis("off")
    axes[1,0].imshow(before, cmap="gray"); axes[1,0].set_title("Before U-Net mask")
    axes[1,1].imshow(after_mask, cmap="gray"); axes[1,1].set_title("After U-Net mask")
    axes[1,2].imshow(av, cmap="gray"); axes[1,2].imshow(colors); axes[1,2].set_title("Change classes")
    for ax in axes[1]: ax.axis("off")
    axes[1,2].legend(handles=[Patch(color="#ff261a",label="Newly segmented"),
      Patch(color="#268cff",label="Receded segmented"),Patch(color="#f2c71a",label="Persistent segmented")],
      loc="lower right",fontsize=8)
    figure_path=root/"before_after_comparison.png"
    fig.savefig(figure_path,dpi=180,bbox_inches="tight"); plt.close(fig)
    report["comparison_figure"]=str(figure_path)
    (root/"comparison_summary.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pair-dir",type=Path,default=Path("outputs/before_after_India_1017769"))
    print(json.dumps(compare(p.parse_args().pair_dir),indent=2))
if __name__=="__main__": main()
