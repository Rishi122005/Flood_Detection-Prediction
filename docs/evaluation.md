# Evaluation

`scripts/evaluate_model.py` evaluates predictions against actual paired Sen1Floods11 hand labels. It does not create or infer labels. Label value `-1` is unknown, `0` non-flood, and `1` flood. Evaluation excludes unknown labels and invalid SAR pixels.

## Reproduce the India test evaluation

```bash
python scripts/evaluate_model.py --split splits/flood_test_data.txt \
  --country India --prediction-dir outputs/india/predictions \
  --threshold 0.5 --output-dir outputs/india/metrics
```

The evaluator requires matching image/label shapes and CRS and allows only a `1e-10` affine tolerance for serialization rounding. The probability raster must also match the source image grid. The threshold is fixed at 0.5 for the recorded test result; test data were not used for threshold selection.

## Metrics

Per-scene and pooled confusion counts are reported as TP, TN, FP, and FN. Precision, recall, Dice/F1, IoU, accuracy, and specificity use zero-safe divisions. A pooled/micro metric is calculated from total pixel counts; macro scene metrics are the unweighted mean of each evaluated scene's score. This distinction matters when scenes contain different numbers of valid pixels.

## Recorded run

The official test file contains 90 IDs, including 14 India IDs. All 14 India test scenes were evaluated in the current run; zero were skipped. At threshold 0.5, pooled metrics were precision 0.8903, recall 0.6584, Dice/F1 0.7570, IoU 0.6090, accuracy 0.9100, and specificity 0.9781 (TP=451,970; TN=2,481,987; FP=55,674; FN=234,537). Macro scene means were precision 0.6554, recall 0.2832, Dice/F1 0.3045, IoU 0.2578, accuracy 0.9152, and specificity 0.9514.

Results and audit artifacts:

- `outputs/india/metrics/per_image_metrics.csv` — per-scene pixel counts and metrics.
- `outputs/india/metrics/summary.json` and `summary.md` — split counts, skip information, micro and macro metrics.
- `outputs/india/metrics/evaluation_figures/` — SAR, ground truth, predicted mask, and overlay for each evaluated test scene.
- `outputs/india/metrics/per_scene_metric_comparison.png` — F1/Dice and IoU by scene.

These are scores for a 14-scene Sen1Floods11 India subset, not nationwide validation. The checkpoint's recorded training log contains one epoch; the large difference between micro and macro recall/Dice indicates that scene-level performance is uneven. Previously stored aggregate metrics under `outputs/test_results.json` are historical and are not used as the reproduced scores here.
