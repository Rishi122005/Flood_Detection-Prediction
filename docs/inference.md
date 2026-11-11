# Local inference

The supported local prediction workflow is `scripts/predict_flood.py`. It uses `models/best_unet_flood.keras` by default and does not download data, train a model, or require Google Colab.

## Input requirements

- A readable GeoTIFF with two bands in VV, VH order. If band descriptions are present, they must identify VV and VH in that order.
- The model expects two channels, in `(512, 512, 2)` patches. Larger rasters are tiled with overlap; smaller edge tiles are padded and cropped to their original extent.
- VV is clipped/scaled from `[-30, 0] dB`, VH from `[-35, -5] dB`, each to `[0, 1]`.
- Non-finite, masked, and nodata input pixels are zero-filled for the model and excluded from counts and area estimates.

## Predict a scene

From the repository root:

```bash
python scripts/predict_flood.py data/S1GRDHand/India_900498_S1Hand.tif \
  --model models/best_unet_flood.keras \
  --output-dir outputs/india/predictions --threshold 0.5
```

The script writes a probability GeoTIFF, a binary mask (`0` non-flood, `1` predicted flood, `255` invalid), a PNG with VV/VH/probability/overlay panels, a per-scene JSON summary, and an upserted `predictions.csv`. Source CRS and transform are copied to the raster outputs. Geographic grids use EPSG:6933 equal-area coordinates for pixel footprints; projected grids use affine area and CRS linear units. Area is unavailable without a usable CRS.

## Discover India scenes

India is identified by a case-insensitive `India` filename token and confirmed as a readable two-band raster. Discovery does not infer a city or event from the benchmark filename.

```bash
python scripts/predict_flood.py --discover-india --max-images 1 \
  --output-dir outputs/india/predictions
```

The discovery default is one image. Pass an explicit positive limit to process a small batch, or `--max-images 0` to process all discovered scenes. In discovery mode, output files are checkpointed after each scene and `scene_processing_status.csv` records processed, reused, and skipped scenes with reasons. Existing predictions are reused only when raster grids, validity masks, finite values, and thresholded masks match the source.

TensorFlow uses an accessible GPU automatically and otherwise uses CPU. CPU thread counts are limited to two by default to avoid oversubscribing this environment.
