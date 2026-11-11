"""Diagnostic, no-artifact 24-hour river-level backtest for CWC telemetry.

This is continuous gauge-level regression only; it does not predict flooding.
The upstream source is scanned linearly and only one station is retained.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .cwc_telemetry import EXPECTED_COLUMNS, _number, parse_observation_time

HFL_METRES = 13.11  # Alipingal historical HFL listed by CWC; used only as conservative QC screen.


def read_station_series(path: Path, station: str = "Alipingal", upper_level_m: float = HFL_METRES):
    """Stream the source CSV; return median duplicate-collapsed values in [0,HFL]."""
    observations = defaultdict(list)
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if (row.get(EXPECTED_COLUMNS["station"]) or "").strip().casefold() != station.casefold():
                continue
            timestamp = parse_observation_time(row.get(EXPECTED_COLUMNS["timestamp"], ""))
            value = _number(row.get(EXPECTED_COLUMNS["level"], ""))
            if timestamp is not None and value is not None and 0 <= value <= upper_level_m:
                observations[timestamp].append(value)
    return {t: float(np.median(vals)) for t, vals in observations.items()}


def make_examples(series, horizon_hours=24):
    """Examples use only t, t-1h, t-6h and t-24h; target is exactly t+24h."""
    examples = []
    for issue in sorted(series):
        if issue.hour != 0 or issue.minute != 0 or issue.second != 0:
            continue
        lags = [issue - timedelta(hours=h) for h in (24, 6, 1, 0)]
        target_time = issue + timedelta(hours=horizon_hours)
        if any(t not in series for t in lags) or target_time not in series:
            continue
        current = series[issue]
        previous_1, previous_6, previous_24 = series[lags[2]], series[lags[1]], series[lags[0]]
        x = np.array([current, current - previous_1, current - previous_6,
                      current - previous_24], dtype=float)
        examples.append({"issued_at": issue, "target_at": target_time,
                         "features": x, "target": series[target_time]})
    # issue times are daily, hence independent target timestamps do not overlap.
    return examples


def chronological_year_split(examples):
    return {year: [e for e in examples if e["issued_at"].year == year]
            for year in (2021, 2022, 2023)}


def ridge_fit_predict(train, evaluation, alpha=1.0):
    x = np.stack([e["features"] for e in train])
    y = np.asarray([e["target"] for e in train], dtype=float)
    mu, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1.0
    z = (x - mu) / scale
    design = np.column_stack([np.ones(len(z)), z])
    penalty = np.eye(design.shape[1]) * alpha
    penalty[0, 0] = 0.0
    coef = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    ev = (np.stack([e["features"] for e in evaluation]) - mu) / scale
    return np.column_stack([np.ones(len(ev)), ev]) @ coef


def error_metrics(actual, predicted):
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    errors = predicted - actual
    return {"mae_m": float(np.mean(np.abs(errors))),
            "rmse_m": float(np.sqrt(np.mean(errors ** 2)))}


def evaluate(series):
    examples = make_examples(series)
    splits = chronological_year_split(examples)
    train, validation, test = (splits[y] for y in (2021, 2022, 2023))
    result = {"status": "diagnostic_only", "target": "continuous CWC Alipingal gauge level exactly 24 hours after issue time",
              "not_a_flood_prediction": True, "threshold_screen": "retained values 0–13.11 m (CWC listed historical HFL); excluded readings require source QC and are not treated as labels",
              "split": {str(y): len(rows) for y, rows in splits.items()},
              "all_available_examples_by_year": {str(year): sum(e["issued_at"].year == year for e in examples)
                                                 for year in sorted({e["issued_at"].year for e in examples})},
              "model_artifact_saved": False, "ridge_alpha": 1.0}
    if not train or not validation or not test:
        result["reason"] = "Insufficient examples in fixed chronological 2021/2022/2023 splits."
        return result
    y_test = [e["target"] for e in test]
    persistence = [e["features"][0] for e in test]
    ridge = ridge_fit_predict(train, test)
    result["validation_samples_not_used_for_fit_selection"] = len(validation)
    result["test_year"] = 2023
    result["test_issue_start"] = min(e["issued_at"] for e in test).isoformat()
    result["test_issue_end"] = max(e["issued_at"] for e in test).isoformat()
    result["test_target_range_m"] = [float(min(y_test)), float(max(y_test))]
    result["persistence"] = error_metrics(y_test, persistence)
    result["ridge"] = error_metrics(y_test, ridge)
    result["ridge_better_than_persistence"] = result["ridge"]["mae_m"] < result["persistence"]["mae_m"]
    result["reason"] = "Diagnostic sample is small and covers only a near-constant low-stage regime; not suitable as a deployed forecast."
    return result
