# Inference preprocessing

The local pipeline accepts a two-band SAR GeoTIFF with band 1 VV and band 2 VH. If raster band descriptions are present, `scripts/predict_flood.py` checks that they identify VV and VH in that order.

## Validity handling

VV/VH must both be finite and readable according to the raster validity masks. Raster nodata values are excluded as well. Invalid pixels are replaced with zero for model input; the original validity mask is retained so those pixels do not contribute to flood-pixel counts, percentage coverage, or physical area.

## Band normalization

The saved notebook's `normalize_bands()` helper and the local script use fixed, independent clipping/scaling:

```text
VV_norm = clip((VV + 30) / 30, 0, 1)   # dB range [-30, 0]
VH_norm = clip((VH + 35) / 30, 0, 1)   # dB range [-35, -5]
```

Channels are stacked in VV, VH order as `float32`. The model expects 512×512×2 patches. Larger images use overlapping tiles and the overlapping probability values are averaged. Smaller edge tiles are padded before inference and cropped back to their original dimensions.

## Labels

For supervised evaluation, hand labels use `-1` for unknown, `0` for non-flood, and `1` for flood. Unknown labels and invalid SAR pixels are excluded from all evaluation metrics. No resizing is performed for matching benchmark labels: dimensions and georeferencing must align with the SAR raster.

The notebook includes additional training-time augmentation and Colab acquisition code. Those steps are not part of the local inference CLI, and the available one-epoch training log is insufficient to independently establish the full preprocessing provenance of the saved model.
