# Floor survey results

Made by `tests/survey_analyze.py` on 2026-11-20 12:15. Do not edit by hand, run the script again.

## Setup

| What | Value |
|---|---|
| Fob | FOB-001 |
| Phone marks | 21 (`survey_2026-11-20_1146.csv`) |
| Survey points in the time range | 21 |
| Matched (mark and point within 60 s) | 21 |
| With a height | 21 |
| Reference readings | 101 |
| Sensor offset taken off | -104.8 Pa (from sensor_offsets.json) |
| Margin to call two floors apart | 1.0 m |

Heights are meters above the Reference board (academic building, floor 1). Negative means below it.

## Heights by building and floor

### Residential

| Floor | Points | Mean (m) | Min (m) | Max (m) | Spread (m) | Mean (Pa) |
|---|---|---|---|---|---|---|
| 0 | 3 | -5.9 | -6.7 | -5.5 | 0.7 | +68.8 |
| 1 | 2 | -0.3 | -0.4 | -0.3 | 0.1 | +3.8 |
| 2 | 3 | +4.2 | +4.0 | +4.4 | 0.2 | -48.3 |
| 3 | 3 | +7.8 | +7.6 | +8.2 | 0.4 | -90.8 |

### Academic

| Floor | Points | Mean (m) | Min (m) | Max (m) | Spread (m) | Mean (Pa) |
|---|---|---|---|---|---|---|
| 1 | 4 | +0.0 | -0.1 | +0.2 | 0.1 | -0.4 |
| 2 | 3 | +4.7 | +4.7 | +4.7 | 0.0 | -54.4 |
| 3 | 3 | +9.0 | +8.8 | +9.1 | 0.2 | -103.9 |

## Neighboring floors

Gap is the difference of the means. Clear is the lowest point of the upper floor minus the highest point of the lower floor. Split is halfway between those two, a first threshold for the floor table.

| Building | Floors | Gap (m) | Clear (m) | Split at (m) | Told apart? |
|---|---|---|---|---|---|
| Residential | 0 to 1 | 5.6 | +5.1 | -2.9 | yes, 5.1 m clear |
| Residential | 1 to 2 | 4.5 | +4.3 | +1.9 | yes, 4.3 m clear |
| Residential | 2 to 3 | 3.7 | +3.2 | +6.0 | yes, 3.2 m clear |
| Academic | 1 to 2 | 4.7 | +4.5 | +2.4 | yes, 4.5 m clear |
| Academic | 2 to 3 | 4.3 | +4.1 | +6.8 | yes, 4.1 m clear |

With 3 points per floor this is a first look. A floor that is only just clear needs more points.

## WiFi

Strongest known access point points to the right building: **14 of 21** points (67%). 7 points heard no access point the other points knew.
Each point is checked against the other points only, so it never grades itself.

| Building | Right | Points | No known access point |
|---|---|---|---|
| Residential | 7 | 11 | 4 |
| Academic | 7 | 10 | 3 |

| Building | Floor | Points | Access points seen | Most seen networks | Strongest signal (median dBm) |
|---|---|---|---|---|---|
| Residential | 0 | 3 | 42 | ASCTE_2 (8), (hidden) (7), ASCTE-IT (6) | -62 |
| Residential | 1 | 2 | 30 | (hidden) (6), ASCTE (5), ASCTE_2 (5) | -52 |
| Residential | 2 | 3 | 39 | (hidden) (9), ASCTE (6), ASCTE_2 (6) | -54 |
| Residential | 3 | 3 | 40 | (hidden) (8), BYOD (8), ASCTE_2 (7) | -65 |
| Academic | 1 | 4 | 51 | (hidden) (11), ASCTE-IT (10), ASCTE-Staff (10) | -65 |
| Academic | 2 | 3 | 45 | (hidden) (12), ASCTE (6), ASCTE-IT (6) | -63 |
| Academic | 3 | 3 | 38 | (hidden) (12), ASCTE (6), ASCTE-IT (6) | -67 |

## Every matched point

| Mark | Time | Building | Floor | Spot | Gap (s) | Fob (Pa) | Reference (Pa) | Height (m) |
|---|---|---|---|---|---|---|---|---|
| 1 | 11:46:01 | Academic | 1 | floor 1 hallway one end | 17 | 99889.9 | 99994.3 | -0.0 |
| 2 | 11:47:17 | Academic | 1 | floor 1 hallway middle | 0 | 99894.9 | 100001.2 | +0.1 |
| 3 | 11:48:17 | Academic | 1 | floor 1 hallway other end | 0 | 99892.1 | 99998.9 | +0.2 |
| 4 | 11:49:49 | Academic | 2 | floor 2 hallway one end | 0 | 99832.2 | 99991.9 | +4.7 |
| 5 | 11:50:48 | Academic | 2 | floor 2 hallway middle | 0 | 99832.3 | 99991.4 | +4.7 |
| 6 | 11:51:52 | Academic | 2 | floor 2 hallway other end | 1 | 99830.1 | 99989.0 | +4.7 |
| 7 | 11:53:28 | Academic | 3 | floor 3 hallway one end | 1 | 99774.0 | 99985.0 | +9.1 |
| 8 | 11:54:19 | Academic | 3 | floor 3 hallway middle | 0 | 99775.7 | 99982.9 | +8.8 |
| 9 | 11:55:17 | Academic | 3 | floor 3 hallway other end | 0 | 99773.9 | 99981.9 | +8.9 |
| 10 | 11:57:29 | Residential | 3 | floor 3 hallway one end | 0 | 99775.7 | 99976.1 | +8.2 |
| 11 | 11:58:28 | Residential | 3 | floor 3 hallway middle | 1 | 99780.5 | 99974.0 | +7.6 |
| 12 | 11:59:25 | Residential | 3 | floor 3 hallway other end | 0 | 99778.1 | 99971.1 | +7.6 |
| 13 | 12:00:30 | Residential | 2 | floor 2 hallway other end | 0 | 99817.3 | 99969.1 | +4.1 |
| 14 | 12:01:29 | Residential | 2 | floor 2 hallway middle | 2 | 99809.8 | 99965.7 | +4.4 |
| 15 | 12:02:18 | Residential | 2 | floor 2 hallway one end | 2 | 99812.6 | 99964.3 | +4.0 |
| 16 | 12:03:23 | Residential | 0 | floor 0 hallway one end | 1 | 99923.1 | 99963.2 | -5.6 |
| 17 | 12:04:15 | Residential | 0 | floor 0 hallway middle | 0 | 99920.3 | 99961.1 | -5.5 |
| 18 | 12:05:16 | Residential | 0 | floor 0 hallway other end | 0 | 99931.4 | 99958.6 | -6.7 |
| 19 | 12:06:08 | Residential | 1 | floor 1 hallway other end | 1 | 99856.0 | 99956.5 | -0.4 |
| 20 | 12:08:08 | Residential | 1 | floor 1 hallway one end | 2 | 99852.9 | 99954.4 | -0.3 |
| 21 | 12:11:31 | Academic | 1 | Next to reference | 1 | 99844.1 | 99947.6 | -0.1 |

