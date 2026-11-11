# Future flood forecasting data assessment

## Local resources

The current checkout has a 122,693-row DesInventar geocoded event catalogue and the Sen1Floods11 SAR, hand-label, optical, DEM, and water-history benchmark subsets. These support historical reports and snapshot flood segmentation. They do not provide issue-time weather and river observations paired with flood onsets and complete non-event observation windows.

The two local GRIBs were inventoried in `outputs/forecasting/glofas_inventory.json`. The 60 control forecast records in `data/glofas/data.grib` cover issue cycles from 2025-01-01 to 2025-01-20, with valid intervals ending by 2025-01-23. `data1.grib` contains two 2016 analysis-type messages. They are not a matched, continuous discharge observation series, and the forecast data is stale for current inference. No local rainfall or meteorological forecast time series were found. A CWC Mahanadi station-level water observation CSV is now available at `data/observations/cwc_mahanadi_telemetry_2021_2025.csv`; its detailed streaming audit is in `reports/cwc_dataset_audit.md`. The CSV lacks danger thresholds, has substantial gaps, and includes unexplained extreme readings, so it is not yet a validated event-label source.

## External source review

| Source | What it provides | Why it does not presently enable this project's flood-event model |
|---|---|---|
| [Google Groundsource dataset](https://zenodo.org/records/18647054) | Open global archive described by Google as 2.6 million news-derived flood events across 150+ countries. Zenodo lists a 667.1 MB Parquet file. | It is an event archive, not complete flood/no-flood surveillance or an environmental predictor archive. A license is not populated in the visible Zenodo record metadata. Downloading it would add a large positive-only source without fixing the label or predictor gap, so it was not downloaded. Google's manual review reports varying event-location/time precision, which would need filtering and uncertainty handling. |
| [Google Runoff Reanalysis & Reforecast (GRRR)](https://sites.research.google/gr/floodforecasting/resources/) | Global river-discharge estimates for 1980–2023. | Modelled discharge alone is not observed flood onset or urban inundation. The local project has no independently validated flood thresholds/matched events for a valid flood-event label. |
| Google Flood Forecasting API | External forecast product; programmatic access is requested through Google and requires a Google account; documented terms include CC BY 4.0. | No authorized credentials or API access are configured. An external vendor forecast would also need to be labelled as such, not as this project's trained model. |
| ERA5/ERA5-Land, IMERG, CHIRPS | Potential historical meteorological predictors. | Predictors cannot remedy missing verified negative/event surveillance. No weather data was downloaded because it would not produce trainable, defensible flood-occurrence labels by itself. |

Google's published Groundsource description reports a 2000-to-present news archive and says manual review found 60% of extracted events accurate in both location and timing and 82% practically useful at administrative-area/day granularity. This is meaningful positive-event evidence but does not make the records a pixel-accurate inundation mask or a complete daily event census. See [Google Research's dataset announcement](https://research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/) and [Google's flood forecasting resources](https://sites.research.google/gr/floodforecasting/resources/).

## Training decision

No supervised future flood-occurrence model was fitted. This is a data-readiness decision, not a failed fit: the model training gate receives zero valid labelled samples and refuses training. Sampling unreported dates as negatives would violate the project's no-fabricated-negative rule. The existing guarded 24-hour pipeline requires both source-attributed pre-issue predictors and evidence of continuous no-flood surveillance for negative windows; the local feature/event/coverage templates do not contain those data.

The API therefore returns `future_flood_event_prediction.status = unavailable` and `probability = null`, with the missing inputs enumerated. Historical report proximity, U-Net segmentation score, and GloFAS discharge remain separate data layers.

## Minimum data needed to train

1. Timestamped rainfall/weather forecast or gauge inputs available at forecast issue time for each location.
2. Observed flood onset labels with location/time uncertainty, matched to an explicit 24-hour or 72-hour horizon.
3. Verified non-event surveillance covering entire target windows at the same supported locations.
4. For riverine outcomes, gauge/catchment linkage and documented flood stage/flow thresholds validated against observed impacts; discharge alone must not be called urban flooding.
5. Enough geographically independent locations and years for chronological plus spatial/event-grouped validation and held-out testing.

