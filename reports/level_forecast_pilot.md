# CWC river-level regression pilot

**Diagnostic continuous-level regression only; this is not a flood prediction.**

- Station: Alipingal (CWC Mahanadi telemetry)
- Source timestamps: timezone unspecified; treated as naive recorded wall-clock values
- Quality screen: retained levels from 0 through 13.11 m. This is a conservative screen based on the published historical HFL, not a claim that higher values are impossible.
- Features: gauge level at issue and differences from exactly 1, 6, and 24 hours before issue.
- Target: observed gauge level exactly 24 hours after issue.
- Split: train 2021, validation 2022, test 2023; no random split; no artifact persisted.
- Counts by year: `{"2021": 151, "2022": 28, "2023": 28}`

- Independent test windows: 28
- Test target range: 4.001000–4.002000 m
- Persistence MAE/RMSE: 0.000142857 / 0.000377964 m
- Ridge MAE/RMSE: 0.000366459 / 0.000422889 m
- Ridge better than persistence by MAE: False

Assessment: Diagnostic sample is small and covers only a near-constant low-stage regime; not suitable as a deployed forecast.

This pilot excludes readings above the historical-HFL screen because their provenance is unresolved. CWC must confirm whether these are corrupt, datum/encoding errors, or genuine new extremes. The 2023 test sample is too small and narrow-stage to support deployment. The model is not integrated into the dashboard and no flood probability is produced.
