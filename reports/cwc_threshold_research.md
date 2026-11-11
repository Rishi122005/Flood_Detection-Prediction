# CWC Mahanadi station threshold and forecasting readiness

## Decision

**Alipingal (also written Alipingala; Devi River, Jagatsinghpur, Odisha) is the best threshold-oriented candidate in this local CWC extract.** The RAJIM station is the coverage leader, but its published gauge datum is not a danger threshold and no RAJIM warning/danger threshold was located in the authoritative sources reviewed. The Alipingal threshold is verified, but the local telemetry is not currently trustworthy enough to train a threshold model: it contains unexplained values far above the published historical high, its coordinate differs materially from CWC station metadata, and the usable chronological samples are sparse with no recent independent test period.

No threshold-exceedance model was trained, and the API must continue to report future flood-event predictions as unavailable with a null probability.

## Authoritative station evidence

The Government of Odisha Department of Water Resources flood bulletin dated 28 June 2025 lists the **Devi River, Alipingala** warning level as **10.85 m**, danger level as **11.76 m**, and historical highest recorded level as **13.05 m on 20 September 2008**. CWC's 2024 flood-forecasting appraisal independently lists Alipingal/Devi warning 10.85 m, danger 11.76 m, and HFL 13.11 m. These are official station-specific reference levels, not thresholds inferred from the CSV.

The source CSV's Alipingal rows report `RL_of_zeroGauge=0.0`, `MeanSeaLevel=15.0`, and coordinates **20.22083333 N, 86.14666667 E**. CWC's Mahanadi Water Year Book station table gives Alipingal Devi at approximately **20°10′ N, 86°10′ E** (20.1667, 86.1667), approximately 6 km from the telemetry coordinate. The available publication establishes station coordinates and the warning/danger/HFL references, but the exact vertical datum and whether the CSV's displayed levels use the same reference have not been reconciled. CWC must confirm station identity, coordinates, datum, and telemetry quality before labels can be accepted.

RAJIM has the strongest raw completeness in the extract: **34,936 records**, **76.122% recorded-hour coverage**, and a **2,077-hour longest gap**, with telemetry coordinates 20.975000 N, 81.880556 E. CWC's Mahanadi water-year book lists its zero gauge at **275 m MSL** and classifies it as a gauge/discharge/sediment/water-quality station. This supports interpretation of RAJIM's gauge datum, but does not supply a danger threshold for that station. Its coverage is not sufficient to establish forecast readiness.

## Alipingal telemetry quality

The station-specific scan found 13,260 source rows from `2021-01-01 00:00` through `2024-05-09 04:00` in the file's recorded timestamp values, four duplicate timestamps, about 40.962% recorded-hour coverage, and a longest observation gap of 4,313 hours. The source provides no timezone declaration; timestamps must remain naive wall-clock values, not be described as UTC.

There are **15 numeric readings at or above 11.76 m** in the raw Alipingal subset, and all 15 are above the published 13.11 m historical high (maximum 891.185 m). The largest readings are not safely interpretable as real river stage without source QC. Conversely, the HFL is a historical record, not a mathematical physical ceiling; values above it must not simply be discarded as false labels. CWC must identify whether these are encoding, datum, sensor, station-key, or genuine new-extreme records. Until then, using them as positive exceedance labels would be indefensible.

Using an explicitly conservative screen that retains 0–13.11 m only, the exact-lag, midnight-issue 24-hour examples are very sparse: **127 (2021 train), 19 (2022 validation), 14 (2023 test)**. There are no usable 2024/2025 Alipingal observations in this file period and no danger crossings in the retained examples. These data cannot support a threshold classifier with both classes or a sufficiently independent recent holdout.

## Continuous level-regression diagnostic

The reproducible pilot in `scripts/evaluate_cwc_level_forecast.py` predicts continuous Alipingal gauge level at `t+24h` from only the observed level at `t`, and differences at `t−1h`, `t−6h`, and `t−24h`. It median-collapses duplicate timestamps, requires exact lag and target observations, keeps one midnight issue per day, uses calendar years for chronological train/validation/test, fits standardization on training data only, and compares a NumPy Ridge regressor with persistence (`level(t+24h)=level(t)`). It does **not** use or predict flood labels.

The initial diagnostic run produced 127/19/14 examples. Its 2023 targets were only 4.000–4.002 m; the independent test is tiny and represents a near-constant low-stage regime. Ridge was worse than persistence on both MAE and RMSE. Metrics are reproduced in `reports/level_forecast_pilot.json` and `.md`; no artifact was saved. This is not an operational river-level forecast and certainly not an urban flood forecast.

## Predictors and task boundaries

The local GloFAS files do not supply genuinely time-aligned historical features for these gauge examples. `data.grib` contains forecast cycles ending in January 2025 and the relevant grid is not matched to this gauge; `data1.grib` contains analysis data from 2016. A GloFAS forecast is usable retrospectively only when its issue time is at or before the gauge forecast issue time and its valid window aligns with the target. Those conditions are not met for these examples. No local timestamped rainfall series was found.

Even a correctly forecast river gauge threshold crossing represents a **river-stage hazard at that gauge**, not proof of urban inundation in a city. Urban flood prediction would require independently verified inundation/event outcomes and spatially matched surveillance, plus suitable rainfall/drainage/exposure inputs.

## Minimum next action

Request from CWC/NWIC the Alipingal telemetry quality-control flags or corrected series, confirmation that the telemetry station key corresponds to the official Alipingala gauge, its coordinate and vertical datum/reference, timestamp timezone, and an explanation/correction for the 15 readings above 13.11 m. Then obtain a longer verified series including several genuine high-water events and recent held-out periods, plus continuous monitoring coverage for non-event periods. For an occurrence model, the cleaned data must contain independently evaluable threshold-positive and observed non-exceedance groups. Add rainfall/discharge predictors only with issue/valid timestamps and spatial matching.

For a continuous level model, the same corrected station identity/datum and quality-controlled timestamped series are essential. A larger number of independent chronological test windows spanning changing river stages is needed; if possible, validate on a later monsoon/event period. Until that evidence exists, no model should be integrated into the dashboard as a forecast.

## Sources

- [Odisha Department of Water Resources, Flood Bulletin, 28 June 2025](https://dowr.odisha.gov.in/sites/default/files/2025-06/DoWR%20Flood%20Bulletin_28.06.2025.pdf): Alipingala warning 10.85 m, danger 11.76 m, recorded HFL 13.05 m dated 20 September 2008.
- [Central Water Commission, Flood Forecasting Network Appraisal Report 2024](https://cwc.gov.in/sites/default/files/appraisal-report-2024-publicationcompressed.pdf): Alipingal Devi warning 10.85 m, danger 11.76 m, HFL 13.11 m.
- [Central Water Commission, Mahanadi Water Year Book 2015–16](https://cwc.gov.in/sites/default/files/admin/7a-mero-bhubaneshwar-mahanadi-wyb-2015-16.pdf): Mahanadi station list and Rajim zero gauge 275 m MSL; Alipingal station location.
- [NWDP CWC hourly telemetry dataset record](https://nwdp.nwic.gov.in/en/dataset/river-water-level-telemetry-hourly-central-water-commission-cwc): source dataset identification and description.
