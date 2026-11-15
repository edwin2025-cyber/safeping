# Outdoor walk test: Nov 11, 2026

Time: 4:17 PM to 5:02 PM
Setup: Fob on LiPo, worn and carried normally. Relay on the laptop by an academic building window, antenna stood up vertical. Server with MQTT on. Logger in Relay-only mode with `--forward`, so the Fob's own log was not recorded. Firmware 2026.11.11c.
Data: `logs/2026-11-11/160431_outdoor_nov11/` plus the phone notes below.

## Headline

- **47 presses, 47 confirmed.** No fail buzz anywhere on campus, outside or inside.
- 31 went over LoRa (the Relay heard them), the rest over WiFi.
- All four types used: STATUS, SUSPICIOUS, MEDICAL, SILENT.

## 1. GPS accuracy, soccer field (DT-10 extra spot)

True point: 34.7235808, -86.6539513 (maps pin). 5 SUSPICIOUS presses, about 37 s apart, ctr 265 to 269.

| ctr | Error (m) |
|---|---|
| 265 | 2.7 |
| 266 | 2.8 |
| 267 | 2.3 |
| 268 | 2.5 |
| 269 | 2.7 |

Average 2.6 m, worst 2.8 m. All within the 10 m pass line. Reported accuracy (`acc`) was 2 to 3 m.

The courts still have no true-point test. Presses 12 to 21 were at the courts but without a pinned true point.

## 2. Which path each place used

The Relay was by an academic building window.

| Where | Path | Signal at Relay (dBm) | SNR (dB) |
|---|---|---|---|
| Soccer field, corners, entrance | LoRa | -86 to -88 | 8.75 to 9.75 |
| Sidewalk toward soccer field | LoRa | -85 to -86 | 9.25 to 9.5 |
| Courts #2, courts entrance | LoRa | -86 to -93 | 7.5 to 10 |
| Volleyball court (Sentinel Center in the way) | LoRa | -85 to -86 | 9 to 9.5 |
| Courts #1 entrance and center | LoRa | -95 to -98 | 4.5 to 6.5 |
| Courts #1 exit | LoRa | -100 | 1.5 |
| Back of Sentinel, outside wrestling room (ctr 286, 287) | WiFi | not heard by Relay | |
| Back of Sentinel, outside restrooms | LoRa | -101 to -102 | -1.25 to -2.75 |
| Sidewalk next to Sentinel | LoRa | -90 to -95 | 6.5 to 8 |
| Front of Sentinel | LoRa | -84 to -96 | 5.25 to 9.25 |
| Quad center, sidewalk by cafe | LoRa | -77 to -87 | 6.75 to 9 |
| Sidewalk by academic floor 1 | LoRa | -78 | 9.5 to 9.75 |
| Main academic entrance (overhang) | WiFi | | |
| Residential building, floors 2 and 3 | WiFi | | |

Findings:
- **Outside, WiFi almost never reached.** Nearly every outdoor press fell back to LoRa, and LoRa covered the whole walk. So outdoors, LoRa is the main path, not the backup.
- **The weakest spot was behind the Sentinel Center** (-102 dBm, SNR -2.75). It still got through. Courts #1 exit (-100 dBm) "took a lot longer to confirm," which probably means LoRa resends. The Fob log would show it, but it was not recorded.
- Inside the residential building, everything went over WiFi.

## 3. Pressure across campus (for floor detection)

Pressure from the alerts the Relay heard. All within about 30 minutes, so weather drift should be small, but not zero.

| Where | Pressure (Pa) |
|---|---|
| Soccer field and its corners | 98815 to 98826 |
| Courts #2, courts entrance, volleyball | 98814 to 98817 |
| Courts #1 | 98804 to 98808 |
| Back of Sentinel (restrooms side) | 98799 to 98803 |
| Sidewalk next to Sentinel | 98763 to 98769 |
| Quad center, sidewalk by cafe | 98770 to 98772 |
| Front of Sentinel | 98754 to 98757 |
| Sidewalk by academic floor 1 | 98703 to 98710 |

About 12 Pa is 1 m of height. So:
- **The campus is not flat.** The soccer field sits about 10 m below the sidewalk by academic floor 1 (about 115 Pa).
- **The back of the Sentinel Center is about 4 m lower than the front** (about 45 Pa). That fits floor 0 (wrestling room) opening onto the back.
- **The cafe sidewalk (residential ground 0) is about 5 m below academic floor 1** (about 64 Pa), roughly one floor. That fits the idea that residential floors line up one level off from the academic ones, but the indoor survey has to confirm it.
- One `PA_PER_FLOOR` number will not work across buildings. Each building needs its own measured table, against the reference board.

The indoor presses went over WiFi, so their pressure is in the server database, not this log.

## 4. Battery

The battery reading went from 93% (4:17 PM) to 79% (4:46 PM): about 14 points in 30 minutes, with a press every 30 to 60 s. If that rate held, a full charge would last only about 3 to 4 hours of this kind of use. Gauge readings right after a charge can be off, and this was heavy use, so this needs a proper battery test. It is still the biggest open question for a wearable.

## 5. Open items from this test

1. Battery life: a real test, and power saving (GPS, WiFi and the 2 minute help listen all draw power).
2. Courts GPS test with a pinned true point.
3. A way to record the Fob's own log when it is on the LiPo.
4. The indoor survey and the reference board, using these pressure numbers as a starting point.
5. The dashboard now has 34 open test alerts. Test alerts need a clean way to clear or mark them.
