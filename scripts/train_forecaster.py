#!/usr/bin/env python3
"""Train a conservative 24-hour onset baseline only with independent evidence."""
import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from forecasting.pipeline import FEATURES, parse_timestamp


def chronological_group_split(rows):
    """Split whole evaluation groups in time order, preventing group leakage."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["evaluation_group"]].append(row)
    if len(grouped) < 10:
        raise ValueError(f"need at least 10 independent evaluation groups; found {len(grouped)}")
    ordered = sorted(grouped, key=lambda group: min(
        parse_timestamp(row["issued_at"], "issued_at") for row in grouped[group]))
    n = len(ordered)
    train_end, val_end = max(1, int(n * .6)), max(2, int(n * .8))
    if val_end >= n:
        train_end, val_end = n - 2, n - 1
    parts = [sum((grouped[g] for g in ordered[:train_end]), []),
             sum((grouped[g] for g in ordered[train_end:val_end]), []),
             sum((grouped[g] for g in ordered[val_end:]), [])]
    for name, part in zip(("train", "validation", "test"), parts):
        labels = {int(row["label_flood_onset_within_24h"]) for row in part}
        if labels != {0, 1}:
            raise ValueError(f"{name} split needs both flood and non-flood examples; observed labels={sorted(labels)}")
    return parts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("outputs/forecasting/prepared_samples.csv"))
    parser.add_argument("--model", type=Path, default=Path("models/flood_forecaster.joblib"))
    parser.add_argument("--metrics", type=Path, default=Path("outputs/forecasting/training_metrics.json"))
    args = parser.parse_args()
    if args.model.exists():
        parser.error(f"refusing to overwrite existing forecast model: {args.model}")
    if not args.data.is_file():
        parser.error(f"prepared dataset not found: {args.data}; run scripts/prepare_forecast_dataset.py first")
    with args.data.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = set(FEATURES) | {"evaluation_group", "issued_at", "label_flood_onset_within_24h"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            parser.error("prepared dataset missing columns: " + ", ".join(sorted(missing)))
        rows = list(reader)
    try:
        for row in rows:
            if row["label_flood_onset_within_24h"] not in {"0", "1"}:
                raise ValueError("labels must be 0 or 1")
            if not row["evaluation_group"].strip():
                raise ValueError("evaluation_group must be non-empty")
            for name in FEATURES:
                if not math.isfinite(float(row[name])):
                    raise ValueError(f"{name} must be finite")
        train, validation, test = chronological_group_split(rows)
    except (ValueError, TypeError) as exc:
        parser.error(f"training gate failed: {exc}")
    try:
        import joblib
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix,
                                     f1_score, precision_score, recall_score)
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        parser.error(f"training dependency unavailable ({exc}); install scikit-learn and joblib")

    x = lambda part: [[float(row[name]) for name in FEATURES] for row in part]
    y = lambda part: [int(row["label_flood_onset_within_24h"]) for row in part]
    model = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000,
                                                               random_state=42))
    model.fit(x(train), y(train))
    # Validation is reported separately. The 0.5 threshold is fixed in advance;
    # test metrics are computed once and are not used for model selection.
    val_probability = model.predict_proba(x(validation))[:, 1]
    test_probability = model.predict_proba(x(test))[:, 1]
    test_prediction = (test_probability >= .5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y(test), test_prediction, labels=[0, 1]).ravel()
    majority_class = int(sum(y(train)) / len(train) >= .5)
    baseline_prediction = [majority_class] * len(test)
    b_tn, b_fp, b_fn, b_tp = confusion_matrix(y(test), baseline_prediction, labels=[0, 1]).ravel()
    metric_summary = lambda actual, predicted, matrix, probability=None: {
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "f1": float(f1_score(actual, predicted, zero_division=0)),
        "accuracy": float(accuracy_score(actual, predicted)),
        "tn": int(matrix[0]), "fp": int(matrix[1]), "fn": int(matrix[2]), "tp": int(matrix[3]),
        **({"average_precision": float(average_precision_score(actual, probability))} if probability is not None else {}),
    }
    metrics = {
        "status": "trained", "target": "flood onset within 24 hours",
        "features": list(FEATURES), "threshold": 0.5,
        "group_counts": {name: len({row["evaluation_group"] for row in part})
                         for name, part in (("train", train), ("validation", validation), ("test", test))},
        "row_counts": {name: len(part) for name, part in (("train", train), ("validation", validation), ("test", test))},
        "validation_mean_score": float(sum(val_probability) / len(val_probability)),
        "test": {"logistic_regression": metric_summary(y(test), test_prediction, (tn, fp, fn, tp), test_probability),
                 "majority_class_baseline": {"predicted_class": majority_class,
                                             **metric_summary(y(test), baseline_prediction, (b_tn, b_fp, b_fn, b_tp))}},
        "split_policy": "chronological, whole evaluation_group held out; 60/20/20; threshold fixed at 0.5; majority class from training only",
        "validation_caveat": "validation score summary is descriptive; threshold was not tuned",
    }
    args.model.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES, "horizon_hours": 24}, args.model)
    args.metrics.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"Saved forecast model: {args.model}\nTest metrics: {args.metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
