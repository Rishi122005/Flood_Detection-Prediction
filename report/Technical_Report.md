# Global Flood Monitoring and Prediction Using Satellite Data

## Abstract

This project evaluates a U-Net segmentation workflow for flood mapping from two-channel Sentinel-1 SAR imagery (VV and VH). The checkout includes Sen1Floods11 imagery and hand-labeled masks, a saved Keras checkpoint, benchmark split lists, and scripts for tiled inference and label-aware evaluation. The checkpoint loads and produces georeferenced predictions. Its recorded training history contains only one epoch, so results should be viewed as a limited benchmark experiment rather than evidence of an operational system. This report separates current reproducible results from historical stored metrics.

## Introduction and problem statement

Flood extent maps support situational awareness, while optical imagery can be obscured by clouds during flood events. SAR provides an all-weather imaging modality. The project studies whether a convolutional segmentation model can identify flood-labeled pixels from paired VV/VH SAR inputs. The challenge includes class imbalance, ambiguous water-like backscatter, unknown label pixels, and transfer between regions.

## Objectives

1. Load paired SAR and flood-label GeoTIFFs from the supplied benchmark.
2. Apply the model's fixed two-band preprocessing and produce flood probabilities.
3. Quantify performance on matching labels and valid pixels.
4. Preserve source georeferencing and report area only when raster geometry supports it.
5. Make inference and evaluation executable from local Python scripts.

## Dataset and preprocessing

The local dataset is organized under `data/`. The `S1GRDHand` and `LabelHand` directories each contain 446 scenes. SAR files contain two bands identified as VV and VH; labels encode unknown pixels as `-1`, non-flood as `0`, and flood as `1`. Official Sen1Floods11 split ID lists are under `splits/`. The listed split sizes are 252 training, 89 validation, and 90 test items; some IDs may be absent from a subset of modalities, so the evaluator checks file pairs before processing.

India IDs occur in train, validation, and held-out test lists. The test list contains 14 India scenes. These are Sen1Floods11 benchmark scenes, not a nationwide sample and not local imagery of the September 2024 Vijayawada event. `data/vijayawada_sar/` is empty.

Band order is VV then VH. Each channel is independently clipped/scaled to `[0,1]`: VV uses `[-30, 0] dB`, VH uses `[-35, -5] dB`. Non-finite or masked SAR pixels are filled with zero for model input and excluded from statistics. Label pixels below zero and invalid input pixels are excluded from evaluation.

## Model and system architecture

The supplied model is a Keras U-Net with 31,401,921 parameters, input shape `(512, 512, 2)`, and sigmoid probability output shape `(512, 512, 1)`. Inference loads a scene, normalizes VV/VH, uses 512-pixel windows with overlap for larger scenes, averages predictions in overlapping regions, thresholds probabilities at 0.5 by default, and writes georeferenced probability and mask GeoTIFFs plus summaries and visualizations.

```text
VV/VH GeoTIFF → valid-pixel mask → fixed normalization → tiled U-Net
             → probability raster → thresholded flood mask → metrics / map products
```

## Experimental setup

The local execution environment used Python 3.10.12, TensorFlow 2.21.0, and Rasterio 1.4.4. TensorFlow found no accessible GPU; `nvidia-smi` could not access NVML, so inference ran on CPU with TensorFlow thread counts capped at two. At the start of inference, the host reported 32 logical CPUs, 2.94 GiB available memory, and 267.74 GiB free disk. The original checkpoint and its backup were preserved. No training was started. The existing CSV log records one epoch with training Dice 0.2969, validation Dice 0.3474, training loss 0.6422, and validation loss 0.5807. This is insufficient evidence for robust convergence, calibration, or operational readiness.

Case-insensitive filename discovery found 68 compatible two-band India scenes. The inference batch generated 67 predictions and reused one validated cached prediction; no scenes were skipped. The official test split lists 14 India IDs. Evaluation matched `S1GRDHand` with `LabelHand`, checked shape and CRS, and allowed only `1e-10` affine tolerance for serialization rounding. Confusion counts use labeled pixels on valid SAR inputs; unknown labels and invalid inputs are excluded. The threshold is fixed at 0.5. No threshold was tuned against the test set. The evaluation completed all 14 scenes with zero skipped.

## Results and discussion

The model declares input `(512, 512, 2)` and output `(512, 512, 1)`. Across the 14 India test scenes, pooled (micro-averaged) metrics were precision 0.8903, recall 0.6584, Dice/F1 0.7570, IoU 0.6090, accuracy 0.9100, and specificity 0.9781 (TP=451,970; TN=2,481,987; FP=55,674; FN=234,537). Macro-averaged scene metrics were precision 0.6554, recall 0.2832, Dice/F1 0.3045, IoU 0.2578, accuracy 0.9152, and specificity 0.9514. The much lower macro recall and Dice indicate uneven behavior across scenes; pooled metrics are strongly influenced by scenes with more pixels and true positives.

Per-scene precision, recall, Dice/F1, and IoU are shown below. Exact confusion counts and valid-pixel counts are in `outputs/india/metrics/per_image_metrics.csv`.

| Test scene | Precision | Recall | Dice/F1 | IoU |
|---|---:|---:|---:|---:|
| India_900498 | 0.879 | 0.833 | 0.855 | 0.747 |
| India_591317 | 0.935 | 0.921 | 0.928 | 0.866 |
| India_747992 | 0.998 | 0.097 | 0.177 | 0.097 |
| India_79637 | 1.000 | 0.007 | 0.014 | 0.007 |
| India_952728 | 0.746 | 0.008 | 0.015 | 0.008 |
| India_828067 | 0.000 | 0.000 | 0.000 | 0.000 |
| India_570384 | 0.948 | 0.133 | 0.234 | 0.132 |
| India_44475 | 0.000 | 0.000 | 0.000 | 0.000 |
| India_80221 | 0.894 | 0.982 | 0.936 | 0.880 |
| India_1018327 | 0.992 | 0.052 | 0.099 | 0.052 |
| India_592446 | 0.936 | 0.087 | 0.159 | 0.087 |
| India_772630 | 0.000 | 0.000 | 0.000 | 0.000 |
| India_631692 | 0.000 | 0.000 | 0.000 | 0.000 |
| India_399883 | 0.847 | 0.845 | 0.846 | 0.733 |

For `India_900498`, the prediction contains 117,552 flood pixels among 262,144 valid SAR pixels (44.84%). Its equal-area prediction estimate is 10.455 km² of a 23.316 km² valid scene area. This is a model-predicted extent, not ground-truth area. Prediction products for all discovered scenes are under `outputs/india/predictions/`; ground-truth comparison panels for all evaluated test scenes are under `outputs/india/metrics/evaluation_figures/`.

The legacy `outputs/test_results.json` contains previously reported scores (precision 0.8612, recall 0.6082, Dice 0.7129, IoU 0.5539, accuracy 0.9387, specificity 0.9860). These values are historical and are not substituted for the independently reproduced India split results. The checkpoint's short training log and lack of a full training/validation history limit interpretation. A benchmark prediction is not evidence of performance on current Indian flood events.

When a CRS exists, area is calculated from the affine pixel footprint: geographic grid coordinates are transformed to EPSG:6933 (equal-area) and pixel-cell areas are calculated by row; projected grids use the affine determinant with CRS linear-unit conversion. Invalid pixels are excluded. For unreferenced rasters, physical area is reported as unavailable; pixel counts and valid-pixel percentage remain available.

## Limitations

### Historical event catalogue and forecastability

The repository also contains `data/floodevents/DesInventar_Geocoded.csv`, a 122,693-row, 89-country event-report catalogue. Inspection found `GEO_LAT/GEO_LON` to be in geographic ranges for all source rows, whereas original `LAT/LON` include invalid out-of-range values. Dates are mixed month-first and year-first; some encode unknown month/day as zero. The cleaning workflow at `scripts/preprocess_flood_events.py` preserves this date precision, drops only byte-equivalent duplicate records, and emits `outputs/flood_events/desinventar_cleaned.csv`, a preprocessing report, and 1-degree reported-event record counts. The preprocessor records the actual year range, country counts, geocoding methods, and usable-row count in its JSON report.

These records support nearby historical-report lookup and descriptive record-density summaries only. They do not provide continuous non-event observation coverage or exposure denominators. Impact variables are post-event outcomes. Therefore the project does not train a supervised event-occurrence model or publish a future probability from this catalogue. Administrative centroid/fuzzy geocodes are representative points, not flood extents. The API exposes nearby records and their `GEO_METHOD` but does not label the count as risk.

For a defensible future forecast, the project still needs timestamped, location-matched meteorological/hydrological predictors issued before the target window, observed event onsets, and independently documented non-event surveillance coverage, with geographic/event-grouped chronological train, validation, and test splits. GloFAS river discharge alone is not an urban flood label or probability.

- Only one training epoch is documented; the checkpoint may be undertrained.
- No independent Vijayawada September 2024 SAR acquisition is present locally.
- Although all 14 listed India test scenes were evaluated, they are a small benchmark subset and do not establish nationwide geographic representativeness.
- The historical notebook mixes Colab paths, cloud acquisition, training, and exploratory analyses. It was preserved and not run end-to-end.
- There is no provenance sufficient to reproduce the historical aggregate metrics from the stored JSON alone.
- Flood-area estimates derived from model masks are predictions, not authoritative mapped extents.

## Conclusion

The saved model can be loaded and used in a reproducible local inference workflow. The supplied India benchmark scenes enable a held-out label-based India subset evaluation, while the local data do not support a Vijayawada event analysis. Results should be reported with the one-epoch training limitation and the benchmark's geographic scope. Further work should establish training provenance, train and select checkpoints using validation data, and validate independently across events and regions before operational use.

## Future flood prediction: data readiness and implementation

The existing U-Net estimates flood extent for the time represented by its Sentinel-1 input. It has no temporal input, rainfall or hydrology variables, or future target, so its pixel mask cannot be interpreted as a future flood forecast. Local metadata lists one acquisition date for each of 12 benchmark events; India is represented by 2016-08-12. A CWC Mahanadi hourly gauge-level archive is available in `data/observations/cwc_mahanadi_telemetry_2021_2025.csv`; its streaming audit is `reports/cwc_dataset_audit.md`. Official sources publish Alipingal/Devi warning, danger and historical-high levels, but the telemetry has substantial gaps, unresolved readings above HFL, a coordinate discrepancy, and no declared timezone. No local matched rainfall or continuous flood-event surveillance time series was found. A future event model was therefore not trained, and this report provides no future-flood accuracy or probabilities.

A separate continuous-level diagnostic pilot is documented in `reports/level_forecast_pilot.md`. It used leakage-safe exact lag inputs and chronological splits to predict gauge level 24 hours ahead, not flooding. The 28-window 2023 test covered only 4.001–4.002 m; Ridge MAE/RMSE (0.000366459/0.000422889 m) were worse than persistence (0.000142857/0.000377964 m). No model artifact was saved or integrated.

To make the next step reproducible, `forecasting/` and the forecast preparation/training scripts define a 24-hour tabular data-preparation and experimental model path. Inputs require timezone-aware issue/valid/observation timestamps and source attribution. The model feature schema includes matched GloFAS discharge as a separate hydrological input; the point-export CSV is aligned by location and by issue/valid times, and a forecast issued after sample time or not covering the full target is rejected. Positive samples need a documented onset after issue time; negative samples need documented complete surveillance coverage over the target period. Missing surveillance yields an unlabeled row. Training splits whole evaluation groups chronologically, requires both classes in each split, uses a fixed 0.5 threshold, and stores any future model separately from the segmentation model. An absent model produces an explicit unavailable response. These are safeguards and interfaces, not trained forecasting results.

External source investigation found that IMD documents AWS observations and quantitative precipitation forecast products, while CWC describes station forecasts up to 24 hours and basin rainfall-runoff advisories up to seven days. Tamil Nadu's Chennai Flood Monitoring system documents a 72-hour forecast service and associated basin sensors. These establish plausible authorized sources to investigate, but do not establish historical data availability, access rights, or compatibility with local scenes. IMD API endpoint checks in this environment returned HTTP 401; no credentials were available. The forecasting pipeline remains unpopulated pending authorized acquisition and temporal/event matching.

The current data audit also considered the 2026 Google Groundsource archive, described as 2.6 million news-derived flood events from 150+ countries. Zenodo lists a 667.1 MB Parquet artifact, and its visible license metadata is blank. It is a positive event archive, not daily flood-free surveillance, and has no matched environmental predictors, so it was not downloaded. Google's article reports uncertainty in individual event location/time extraction; these reports must not be treated as pixel-level flood boundaries. ERA5 offers hourly global atmospheric reanalysis from 1940 at 0.25° but access through CDS requires a registered account and accepted terms. CHIRPS v3 is open, 0.05° daily precipitation covering 60°S–60°N since 1981; rainfall predictors could be added, but they cannot alone supply valid negative event labels. Source assessment and licensing/access details are recorded in `docs/Forecast_Data_Assessment.md`. The API now returns `not_trained`, a null probability, and these missing-input reasons rather than a generic prediction failure.

Running preparation against the checked-in header-only templates produced zero samples (`outputs/forecasting/prepared_samples.csv`) and a machine-readable `no_labeled_samples` report (`outputs/forecasting/preparation_report.json`). The training gate then correctly refused to fit with zero independent groups. The prediction CLI wrote `outputs/forecasting/latest_prediction.json` with status `unavailable` and a null forecast. These are verified readiness outcomes, not predictive results.

## GloFAS file inventory and global query service

Rasterio/GDAL identified both supplied files as GRIB2. `data/glofas/data.grib` has 60 messages from ECMWF (centre 98), hydrological discipline 1, WMO parameter category 0/number 7, identified as discharge from rivers or streams in m³/s. The records are control forecasts with product template 73 and master table 32: 20 daily initialization times from 2025-01-01 to 2025-01-20 and valid interval ends from 2025-01-02 to 2025-01-23 at 24, 48, and 72 hours. `data/glofas/data1.grib` has two analysis-type messages, product template 72/master table 36, reference time 2016-08-12 and encoded interval end 2016-08-13. Its local template field details are not fully named by GDAL; no station observations or event labels can be asserted from it. Both files share a 7200×3000 EPSG:4326 grid with 0.05° pixels and bounds −180° to 180° longitude and −60° to 90° latitude. Each message uses the same river mask: 6,221,926 valid grid points and 15,378,074 masked points, with GDAL nodata 9999. No duplicate records were found within either file. The files are not concatenated because their product templates, analysis/forecast types, and time ranges differ. The explicit GloFAS release is not exposed in the decoded metadata; the inventory therefore identifies ECMWF hydrological discharge compatible with GloFAS but leaves release/version unknown.

The reproducible inventory is `outputs/forecasting/glofas_inventory.json`. `scripts/export_glofas_point.py` can export all compatible forecast records at the nearest river cell to a coordinate or a GeoTIFF scene center. A smoke test at the georeferenced center of `India_25540_S1Hand.tif` selected a river grid cell 2.137 km away and produced three discharge values (0.234375 m³/s in the local file) for the 24/48/72-hour valid intervals of the latest stored cycle, initialized 2025-01-20. These are actual GRIB values, but the product is stale as of this run and no event probability or risk category is derived. The export is stored in `outputs/forecasting/glofas_point_forecast.csv` with companion metadata JSON.

The local interface is served by the standard-library HTTP server at `scripts/run_server.py`; the UI is `frontend/index.html`, and the backend is `src/flood_app/server.py`. It exposes georeferenced prediction catalog/bounding-box filters and coordinate queries against the available river grid and historical event catalogue. The current satellite prediction catalog has 68 saved India benchmark footprints only; the GloFAS grid provides river-cell lookup across its actual masked coverage, not everywhere. Scene acquisition timestamps are absent from prediction provenance. The former schematic sphere has been replaced by an offline Canvas globe using Natural Earth 1:110m country polygons, coastlines, borders, graticules and ocean/sea labels, with rotation, pointer/scroll/button zoom, coordinate selection and data markers. The bundled map source is public domain; its provenance and checksum are in `frontend/EARTH_DATA.md`. The browser engine is unavailable in the current environment, so interaction/rendering is not claimed as browser-verified; the generated texture and HTTP asset delivery are tested. The API returns a separate explicit unavailable object and null probability for model-generated future flood events. This is a local exploration interface, not an operational warning service.

The ECMWF documentation describes GloFAS river-discharge products and their units; the GRIB parameter database maps 1/0/7 to discharge from rivers or streams in m³/s. It also cautions that gridded rivers can be spatially offset and recommends checking upstream area; that auxiliary layer is absent, so the nearest-cell smoke test verifies file extraction only, not local hydrological representativeness. GloFAS is designed for larger catchments, and skill is less certain in small catchments. The CEMS data terms allow free use subject to conditions, require source attribution for public redistribution, and explicitly say the data are not an official flood warning. The local product templates (72 and 73) remain partly opaque without ecCodes definitions. [GloFAS model output documentation](https://confluence.ecmwf.int/pages/viewpage.action?navigatingVersions=true&pageId=400501522), [ECMWF/WMO parameter 240013](https://codes.ecmwf.int/grib/param-db/240013), [GRIB2 product template registry](https://codes.ecmwf.int/grib/format/grib2/templates/4/), [CEMS-FLOODS terms](https://cds.climate.copernicus.eu/licences/cems-floods).

## References

Bonafilia, D., Tellman, B., Anderson, T., & Issenberg, E. (2020). *Sen1Floods11: A georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1*. IEEE/CVF Conference on Computer Vision and Pattern Recognition Workshops.

Project metadata: `Sen1Floods11_Metadata.geojson`, official split files in `splits/`, model artifact `models/best_unet_flood.keras`, and preprocessing documented in the preserved notebook cell defining `normalize_bands()`.

Indian operational data references consulted for forecast data readiness: [India Meteorological Department API reference](https://api.imd.gov.in/public/api_reference.html); [Central Water Commission flood forecasting services](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2147812&lang=2&reg=48); [Chennai Flood Monitoring FAQ](https://chennaifloodmonitor.tn.gov.in/Master/FAQ); [Chennai Flood Monitoring system overview](https://chennaifloodmonitor.tn.gov.in/Master/AboutUs).

Map source: Natural Earth, 1:110m Admin 0 Countries. The project bundles a GeoJSON copy and generated texture; Natural Earth identifies its vector and raster datasets as public domain. [Natural Earth terms of use](https://www.naturalearthdata.com/about/terms-of-use/); [1:110m physical vectors](https://www.naturalearthdata.com/downloads/110m-physical-vectors/).

Additional flood forecasting sources assessed: [Google Research Groundsource announcement](https://research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/); [Groundsource Zenodo record](https://zenodo.org/records/18647054); [Google flood forecast resources, including GRRR and API access](https://sites.research.google/gr/floodforecasting/resources/); [ERA5 hourly single-level data](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels); [CHIRPS v3 data overview](https://www.chc.ucsb.edu/data/chirps3).
