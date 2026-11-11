# CWC Mahanadi telemetry dataset audit

Source: `/mnt/c/Users/codri/Downloads/Flood-Monitoring-and-Prediction-Using-Satellite-Data-main/data/observations/cwc_mahanadi_telemetry_2021_2025.csv` (148,640,758 bytes).

## Dataset summary

- Records: 921,203
- Station keys (station, agency, district, river): 37
- Valid observation period: 2021-01-01T00:00:00 to 2025-12-30T05:00:00
- Invalid timestamps: 0
- Invalid water-level values: 37
- Negative numeric water levels: 3
- Invalid or missing coordinates: 0
- Duplicate station/timestamp records: 163
- Inter-observation gaps over one hour: 53,848
- Source has danger/warning threshold columns: no

Water-level units are identified as metres in the CSV header. The source does not specify the timestamp timezone; timestamps are retained as naive recorded wall-clock values. The file contains observed water levels only; it does not establish forecast issue time or a verified urban flood-event target.

## Stations

| Station | District | Basin | Coordinates (lat, lon) | Valid rows | First | Last | Hourly coverage | Cadence intervals | Gap intervals | Longest gap (h) | Level min–max (m) | RL of zero gauge (m) | Readings >10m from RL-zero | Candidate decision |
|---|---|---|---|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| RAJIM | GARIABAND | Mahanadi | 20.975000, 81.880556 | 34,936 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 76.122% | 1-hour: 30,075, 30-minute: 3,342, other sub-hour: 122 | 1,392 | 2077.0 | 275.0–1172.21 | 275.0 | 52 | coverage leader only; no verified RAJIM danger threshold, long gaps, and large excursions need CWC clarification |
| Kurubhata | RAIGARH | Mahanadi | 21.981111, 83.210556 | 30,387 | 2021-01-01T00:00:00 | 2025-06-26T18:00:00 | 72.745% | 1-hour: 25,125, 30-minute: 3,464, other sub-hour: 108 | 1,683 | 668.0 | 215.0–1095.003 | 213.5 | 20 | not selected: station-specific threshold and data quality need review |
| Dharamjaigarh | RAIGARH | Mahanadi | 22.477222, 83.214167 | 33,582 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 72.722% | 1-hour: 28,625, 30-minute: 3,557, other sub-hour: 154 | 1,237 | 2079.0 | 270.0–1269.246 | 270.0 | 33 | not selected: station-specific threshold and data quality need review |
| Surajgarh | RAIGARH | Mahanadi | 21.693611, 83.377222 | 33,485 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 72.525% | 1-hour: 28,590, 30-minute: 3,538, other sub-hour: 150 | 1,198 | 2081.0 | 188.0–956.0 | 188.0 | 27 | not selected: station-specific threshold and data quality need review |
| Kelo at Raigarh | RAIGARH | Mahanadi | 21.891111, 83.399167 | 29,989 | 2021-01-01T00:00:00 | 2025-06-13T00:00:00 | 72.291% | 1-hour: 24,765, 30-minute: 3,476, other sub-hour: 124 | 1,616 | 779.0 | 223.0–1241.229 | 223.0 | 608 | not selected: station-specific threshold and data quality need review |
| Jondhra | BILASPUR | Mahanadi | 21.716944, 82.338333 | 32,234 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 70.926% | 1-hour: 28,387, 30-minute: 2,428, other sub-hour: 158 | 1,253 | 2156.0 | 219.0–1227.01 | 219.0 | 53 | not selected: station-specific threshold and data quality need review |
| Parmanpur | JHARSUGUDA | Mahanadi | 21.789444, 84.106111 | 32,097 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 69.349% | 1-hour: 26,676, 30-minute: 3,536, other sub-hour: 154 | 1,727 | 2370.0 | 199.0–1169.006 | 199.0 | 1,546 | not selected: station-specific threshold and data quality need review |
| Andhiyarkhore | BEMETARA | Mahanadi | 21.834722, 81.597222 | 31,948 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 69.062% | 1-hour: 27,050, 30-minute: 3,458, other sub-hour: 170 | 1,258 | 2080.0 | 252.0–1222.009 | 252.0 | 46 | not selected: station-specific threshold and data quality need review |
| Khairmal | BAUDH | Mahanadi | 20.828333, 83.980000 | 30,346 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 66.122% | 1-hour: 25,857, 30-minute: 2,874, other sub-hour: 115 | 1,493 | 2215.0 | 97.56–1059.804 | 97.56 | 24 | not selected: station-specific threshold and data quality need review |
| Basantpur | JANJGIR - CHAMPA | Mahanadi | 21.727500, 82.788056 | 22,290 | 2021-01-01T00:00:00 | 2024-08-13T06:00:00 | 65.847% | 1-hour: 18,004, 30-minute: 2,656, other sub-hour: 172 | 1,449 | 3009.0 | 206.0–710.06 | 206.0 | 39 | not selected: station-specific threshold and data quality need review |
| Jamadarpali | SAMBALPUR | Mahanadi | 21.567222, 83.981667 | 30,191 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 65.666% | 1-hour: 24,336, 30-minute: 2,957, other sub-hour: 135 | 2,760 | 2076.0 | 177.0–1001.086 | 177.7 | 26 | not selected: station-specific threshold and data quality need review |
| Kantamal | BAUDH | Mahanadi | 20.655000, 83.727500 | 29,295 | 2021-01-01T00:00:00 | 2025-12-22T20:00:00 | 64.759% | 1-hour: 24,642, 30-minute: 1,955, other sub-hour: 125 | 2,571 | 2967.0 | 118.0–1118.01 | 118.0 | 51 | not selected: station-specific threshold and data quality need review |
| Seorinarayan | JANJGIR - CHAMPA | Mahanadi | 21.718333, 82.597500 | 28,649 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 63.252% | 1-hour: 25,168, 30-minute: 1,989, other sub-hour: 125 | 1,363 | 2078.0 | 209.5–1184.477 | 209.5 | 122 | not selected: station-specific threshold and data quality need review |
| Simga | BALODABAZAR | Mahanadi | 21.632778, 81.684722 | 29,311 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 63.036% | 1-hour: 24,140, 30-minute: 3,475, other sub-hour: 146 | 1,544 | 2108.0 | 244.0–1181.019 | 244.0 | 4,370 | not selected: station-specific threshold and data quality need review |
| Thethetanger | JASHPUR | Mahanadi | 22.646667, 83.933611 | 28,317 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 61.238% | 1-hour: 23,497, 30-minute: 3,078, other sub-hour: 121 | 1,614 | 2081.0 | 354.0–1122.006 | 354.0 | 29 | not selected: station-specific threshold and data quality need review |
| Kishan Nagar | CUTTACK | Mahanadi | 20.426667, 86.089167 | 30,732 | 2021-01-01T05:30:00 | 2025-12-30T04:30:00 | 60.851% | 1-hour: 21,240, 30-minute: 8,123, other sub-hour: 9 | 1,359 | 5553.0 | 1.024–1010.22 | 0.0 | 30,266 | not selected: station-specific threshold and data quality need review |
| Korba | KORBA | Mahanadi | 22.393333, 82.702778 | 27,054 | 2021-01-05T17:00:00 | 2025-12-23T01:00:00 | 59.885% | 1-hour: 22,531, 30-minute: 1,910, other sub-hour: 81 | 2,526 | 2100.0 | 272.0–1283.17 | 272.0 | 440 | not selected: station-specific threshold and data quality need review |
| Deogaon | SAMBALPUR | Mahanadi | 21.221944, 83.912222 | 24,692 | 2021-01-01T00:00:00 | 2025-05-19T08:00:00 | 59.578% | 1-hour: 19,055, 30-minute: 3,459, other sub-hour: 165 | 2,004 | 3095.0 | 114.0–1026.01 | 114.0 | 44 | not selected: station-specific threshold and data quality need review |
| Ghatora | BILASPUR | Mahanadi | 22.048611, 82.221667 | 27,595 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 59.014% | 1-hour: 22,734, 30-minute: 3,532, other sub-hour: 161 | 1,159 | 4554.0 | 246.0–918.009 | 246.0 | 13 | not selected: station-specific threshold and data quality need review |
| Baronda | GARIABAND | Mahanadi | 20.910556, 81.887222 | 8,892 | 2024-04-04T14:30:00 | 2025-12-30T04:30:00 | 58.381% | 1-hour: 8,249 | 642 | 1120.0 | 284.79–1209.59 | 283.0 | 8,880 | not selected: station-specific threshold and data quality need review |
| RAVISHANKAR SAGAR DAM | DHAMTARI | Mahanadi | 20.610000, 81.560000 | 26,908 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 57.695% | 1-hour: 22,039, 30-minute: 3,342, other sub-hour: 132 | 1,388 | 6965.0 | 4.0–1019.0 | 0.0 | 26,907 | not selected: station-specific threshold and data quality need review |
| Lower Indra Project | BALANGIR | Mahanadi | 20.413900, 82.865300 | 24,481 | 2021-03-03T11:30:00 | 2025-12-30T05:00:00 | 57.671% | 1-hour: 23,017, 30-minute: 157, other sub-hour: 7 | 1,299 | 5954.0 | -246.42–266.7 | 0.0 | 24,481 | not selected: station-specific threshold and data quality need review |
| Tikarpara | ANUGUL | Mahanadi | 20.598889, 84.781389 | 22,974 | 2021-01-03T03:00:00 | 2025-04-06T17:00:00 | 57.669% | 1-hour: 17,896, 30-minute: 2,734, other sub-hour: 155 | 2,182 | 717.0 | 50.0–1027.019 | 50.0 | 272 | not selected: station-specific threshold and data quality need review |
| Bamnidhi | JANJGIR - CHAMPA | Mahanadi | 21.900000, 82.713333 | 26,508 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 57.278% | 1-hour: 22,001, 30-minute: 2,992, other sub-hour: 54 | 1,458 | 8528.0 | 223.0–1087.017 | 223.0 | 33 | not selected: station-specific threshold and data quality need review |
| Sankara | MAHASAMUND | Mahanadi | 21.288889, 82.651389 | 26,694 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 57.255% | 1-hour: 21,333, 30-minute: 3,304, other sub-hour: 123 | 1,924 | 3406.0 | 262.0–1228.939 | 259.0 | 22 | not selected: station-specific threshold and data quality need review |
| Kesinga | KALAHANDI | Mahanadi | 20.198611, 83.219444 | 25,354 | 2021-01-01T00:00:00 | 2025-09-13T12:00:00 | 57.198% | 1-hour: 20,937, 30-minute: 3,524, other sub-hour: 47 | 844 | 4166.0 | 166.0–1128.873 | 166.0 | 31 | not selected: station-specific threshold and data quality need review |
| Salebhata | BALANGIR | Mahanadi | 20.983056, 83.536944 | 26,700 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 57.175% | 1-hour: 21,670, 30-minute: 3,332, other sub-hour: 169 | 1,522 | 9360.0 | 130.0–1015.456 | 127.0 | 15 | not selected: station-specific threshold and data quality need review |
| Rampur | BALODABAZAR | Mahanadi | 21.647222, 82.516111 | 8,671 | 2024-04-04T05:30:00 | 2025-12-30T04:30:00 | 56.896% | 1-hour: 8,048, 30-minute: 1 | 621 | 1120.0 | 220.27–1336.68 | 217.0 | 8,595 | not selected: station-specific threshold and data quality need review |
| Pubansa (S) | CUTTACK | Mahanadi | 20.462778, 86.249167 | 28,103 | 2021-01-01T05:30:00 | 2025-12-17T04:30:00 | 55.319% | 1-hour: 18,511, 30-minute: 8,067, other sub-hour: 12 | 1,512 | 5549.0 | 0.004–1003.015 | 0.0 | 10,107 | not selected: station-specific threshold and data quality need review |
| Manendragarh | KORIYA | Mahanadi | 23.201389, 82.214444 | 23,525 | 2021-01-01T13:00:00 | 2025-12-22T18:00:00 | 53.618% | 1-hour: 21,197, 30-minute: 160, other sub-hour: 122 | 2,040 | 2081.0 | 411.14–1403.528 | 409.5 | 18 | not selected: station-specific threshold and data quality need review |
| Hirakud Reservoir | SAMBALPUR | Mahanadi | 21.520000, 83.850000 | 23,354 | 2021-01-07T09:00:00 | 2025-12-23T00:00:00 | 51.961% | 1-hour: 20,292, 30-minute: 1,425, other sub-hour: 110 | 1,521 | 8126.0 | 161.77–1064.946 | 0.0 | 23,354 | not selected: station-specific threshold and data quality need review |
| Sundergarh | SUNDARGARH | Mahanadi | 22.115278, 83.399167 | 24,377 | 2021-01-01T00:00:00 | 2025-12-23T01:00:00 | 51.768% | 1-hour: 18,779, 30-minute: 3,456, other sub-hour: 125 | 2,009 | 2080.0 | 214.0–1115.939 | 214.0 | 21 | not selected: station-specific threshold and data quality need review |
| Alipingal | JAGATSINGHAPUR | Mahanadi | 20.220833, 86.146667 | 13,260 | 2021-01-01T00:00:00 | 2024-05-09T04:00:00 | 40.962% | 1-hour: 9,368, 30-minute: 2,321, other sub-hour: 90 | 1,476 | 4313.0 | 0.001–891.185 | 0.0 | 17 | threshold-oriented candidate; official levels verified, but extreme telemetry readings, coordinate mismatch, gaps, and datum/timezone need CWC clarification |
| Pilasalki Dam | KANDHAMAL | Mahanadi | 20.423900, 84.338100 | 16,853 | 2021-03-16T12:30:00 | 2025-12-30T04:00:00 | 39.923% | 1-hour: 16,226, 30-minute: 175, other sub-hour: 2 | 449 | 9694.0 | -75.11–548.89 | 0.0 | 16,852 | not selected: station-specific threshold and data quality need review |
| Nimapara | PURI | Mahanadi | 20.060833, 86.006389 | 17,545 | 2021-01-08T06:00:00 | 2025-12-22T04:00:00 | 39.629% | 1-hour: 15,348, 30-minute: 550, other sub-hour: 118 | 1,525 | 5326.0 | 3.22–889.22 | 0.0 | 56 | not selected: station-specific threshold and data quality need review |
| Padmavati | NAYAGARH | Mahanadi | 20.343889, 85.296111 | 9,818 | 2021-01-01T00:00:00 | 2023-08-19T19:00:00 | 35.16% | 1-hour: 6,188, 30-minute: 3,313, other sub-hour: 101 | 212 | 7272.0 | 30.0–646.0 | 30.0 | 2 | not selected: station-specific threshold and data quality need review |
| Khandapara | NAYAGARH | Mahanadi | 20.257500, 85.186111 | 19 | 2021-10-02T08:30:00 | 2022-07-28T03:00:00 | 0.265% | not classified | 18 | 3003.0 | 0.001–768.0 | 45.0 | 18 | not selected: station-specific threshold and data quality need review |

## Assessment and candidate selection

Coverage ranks identify stations for review only. A high record count or hourly coverage does not establish station reliability or flood occurrence. Negative threshold labels also require complete observations throughout the forecast window. Source timestamps carry no timezone declaration; they are preserved as naive recorded wall-clock values.

RAJIM is the coverage leader but is not selected for threshold prediction: its station-specific threshold is not verified here, and it has long gaps and level excursions far above its reported `RL_of_zeroGauge`. Separately, official CWC/Odisha sources publish Alipingal warning/danger/HFL levels; see `reports/cwc_threshold_research.md`. Alipingal's local telemetry contains unresolved readings above that historical HFL, so no threshold model is currently defensible.

`RL_of_zeroGauge` and `MeanSeaLevel` are metadata, not danger thresholds. Threshold exceedance at a river gauge is not equivalent to urban inundation.
