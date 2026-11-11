# Training and checkpoint provenance

The repository contains a saved Keras U-Net at `models/best_unet_flood.keras` and a separate backup at `models/best_unet_flood_backup.keras`. Both files were preserved and their SHA-256 hashes matched during inspection. The active local workflow does not train or modify either file.

## Evidence available in this checkout

`outputs/training_log.csv` contains one recorded epoch:

| Metric | Training | Validation |
|---|---:|---:|
| Dice | 0.2969 | 0.3474 |
| IoU | 0.2170 | 0.2932 |
| Loss | 0.6422 | 0.5807 |

The notebook contains training code and configuration, but the available log does not document a longer run. The checkpoint loads and has input `(512, 512, 2)` and output `(512, 512, 1)`, but loadability and a single log row do not establish adequate training, calibration, or production readiness. Historical aggregate metrics are not a substitute for missing training provenance.

## Dataset splits

The split files list 252 training IDs, 89 validation IDs, and 90 test IDs. The local runtime data contains matching VV/VH inputs and hand labels; the scripts evaluate only the requested split and do not start training.

## Retraining

No retraining command is provided as part of the supported local prediction workflow. Any future training run should save a new checkpoint path, preserve geographic/event separation between splits, document all preprocessing and label-validity rules, and select thresholds/checkpoints using validation data only. Do not overwrite the current checkpoint or its backup.
