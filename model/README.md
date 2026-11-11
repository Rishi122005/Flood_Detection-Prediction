# Saved flood segmentation model

The active checkpoints are in the repository's `models/` directory:

- `models/best_unet_flood.keras` — selected TensorFlow/Keras U-Net checkpoint.
- `models/best_unet_flood_backup.keras` — preserved backup.

The selected model expects float32 Sentinel-1 SAR tiles of shape `512×512×2` in VV, VH order and returns `512×512×1` flood-label probabilities. It has 31,401,921 Keras parameters. Inference clips/scales VV from `[-30, 0] dB` and VH from `[-35, -5] dB` to `[0, 1]`; invalid pixels are excluded from reported area/counts.

The Windows CPU path caches a float32 TFLite conversion of the selected checkpoint in `outputs/model_cache/` and runs it through XNNPACK. This derived cache does not replace or modify either Keras checkpoint. See the root README for inference and dashboard startup commands.
