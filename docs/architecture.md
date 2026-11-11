# Local system architecture

The supported workflow is a Python command-line pipeline around the preserved TensorFlow/Keras U-Net. It does not include a frontend, web server, Google Earth Engine acquisition, rainfall API, permanent-water removal, or risk classifier.

```text
Sen1Floods11 VV/VH GeoTIFF
          │
          ▼
Raster validity + band-order checks
          │
          ▼
Fixed VV/VH clipping and scaling
          │
          ▼
512×512 U-Net tiles with overlap for larger rasters
          │
          ├──► Probability GeoTIFF
          ├──► Thresholded mask GeoTIFF
          ├──► SAR/probability/overlay figure
          └──► Valid-pixel and geospatial area summary
                    │
                    ▼
       Paired ground-truth evaluation on selected split
                    │
          ├──► Per-scene and pooled/macro metrics
          ├──► Ground-truth comparison figures
          └──► Scene-level comparison chart
```

## Model interface

The inspected checkpoint has 31,401,921 parameters, accepts `(512, 512, 2)` VV/VH inputs, and returns `(512, 512, 1)` sigmoid probabilities. TensorFlow selects an accessible GPU automatically; otherwise, the scripts run CPU inference with conservative thread limits.

## Geospatial processing

Output rasters preserve the input dimensions, CRS, and affine transform. Invalid source pixels are excluded from statistics and stored as nodata in prediction rasters. Geographic pixel footprints are transformed to EPSG:6933 for equal-area calculations; projected pixel areas use the affine determinant and CRS unit conversion. Area estimates are model predictions and are not ground-truth extents.

## Acquisition and risk analysis

Cloud acquisition, Vijayawada event compositing, rainfall integration, permanent-water filtering, interactive maps, and risk assessment appear in the legacy notebook/docs but are not verified by the local dataset currently present. The notebook is preserved; the repeatable local workflow uses the scripts documented in the root README.
