# Flood forecast data readiness

## Decision

The CWC telemetry now has an authoritative station threshold for Alipingal/Devi, but **no defensible flood threshold model is ready to train**. The API must report future flood-event probability as unavailable/null. No validated model artifact exists.

## Evidence and station choice

- **Alipingal** is the best threshold-oriented candidate: Odisha DoWR and CWC sources list warning 10.85 m, danger 11.76 m and HFL 13.11 m (see [threshold research](../reports/cwc_threshold_research.md)). The CSV has 13,260 rows, 40.962% recorded-hour coverage, four duplicate timestamps and a 4,313-hour longest gap. Local coordinates (20.220833 N, 86.146667 E) differ by about 6 km from the CWC yearbook station coordinate. Its `RL_of_zeroGauge=0` and `MeanSeaLevel=15` have not been reconciled with the official threshold datum.
- The local station subset contains 15 records at/above the published danger level, all above the 13.11 m historical high; the maximum is 891.185 m. These may be corrupt, datum/encoding errors, or genuine new extremes. Historical HFL is not a physical ceiling, so the readings cannot be silently relabeled as false or discarded for a production model.
- **RAJIM** is the raw coverage leader: 34,936 valid observations, 76.122% recorded-hour coverage, 2,077-hour longest gap. CWC's water-year book gives zero gauge 275 m MSL. This is datum metadata, not a danger threshold; no RAJIM warning/danger threshold was verified.
- CSV timestamps have no declared timezone. Audit and pilot preserve them as naive recorded wall-clock time; earlier audit outputs that named these UTC have been corrected.

## Reproducible continuous-level pilot

`python scripts/evaluate_cwc_level_forecast.py` reads the selected station rows in a streaming pass, median-collapses duplicate timestamps, and retains 0–13.11 m as a conservative diagnostic quality screen. It predicts the observed level exactly 24 hours later from issue-time and prior level differences only. It uses 2021 train, 2022 validation, and 2023 test years; standardization is fitted on training only. It compares persistence with Ridge, writes no model artifact, and makes no flood-risk claim.

Actual pilot result: 151 train / 28 validation / 28 test windows. The 2023 test target range is 4.001–4.002 m. Persistence MAE/RMSE are 0.000142857/0.000377964 m; Ridge MAE/RMSE are 0.000366459/0.000422889 m. Ridge loses to persistence, and the tiny near-constant low-stage test does not establish useful generalization. See `reports/level_forecast_pilot.json` and `.md`.

## What prevents training

1. CWC must confirm Alipingal station identity, coordinates, gauge datum, timestamp timezone, quality flags/corrections and interpretation of readings above HFL.
2. A threshold classifier needs multiple verified threshold events and fully observed non-exceedance periods with enough independent chronological test periods. Under the conservative HFL screen, the available exact-lag examples contain no threshold positives and stop before a recent holdout.
3. Local GloFAS data are not aligned predictors: the forecast archive is stale and not matched to this gauge/issue dates; the analysis file is from 2016. No local matched rainfall time series is present.
4. River-level threshold exceedance is a gauge hazard, not proof of urban inundation. An urban flood target requires geolocated event/inundation labels and continuous non-event surveillance.

## Minimum next action

Request the Alipingal station/time/datum/quality confirmation and corrected telemetry from CWC/NWIC, especially for the 15 values above published HFL. Then evaluate a longer series with independently held-out high-water periods. For an event model, labels must include verified threshold exceedances and complete monitored non-event windows. Add meteorological/hydrological predictors only when their issue times precede the forecast and valid times match the target.

The dashboard has a separate **Experimental Gauge Demo** for Alipingal. It classifies the latest screened historical reading using the published warning/danger thresholds, reports the input timestamp, and emits no probability. It explicitly states that the source observation is stale and that the category is retrospective, not a next-24-hour forecast. This is a transparent interface demonstration, not a trained model or validated future flood prediction. A river-gauge threshold category must not be represented as urban flood risk.
