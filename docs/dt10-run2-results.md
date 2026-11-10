# DT-10 GPS accuracy test: results (run 2, official)

**Date:** Nov 10, 2026, 14:30 to 14:55
**Run folder:** `logs/2026-11-10/143031_official_dt10_run2/`
**Pass criterion** (set Nov 9, before this run): the reported location is within **10 m** of the true spot for at least **95%** of outdoor presses with a GPS fix.

**Setup:**
- The Relay was at the third-floor window, on COM14, with `field_log.py --label official_dt10_run2 --no-fob`.
- The Fob ran on LiPo with WiFi off (LoRa only).
- Presses were SUSPICIOUS (2 quick presses), 30 s apart, 5 per spot.
- True locations were Google Maps satellite pins, preset on the `dt10.html` phone page.

## Result: PASS

**15 of 15 outdoor presses were within 10 m (100%).**

| Spot | Presses (ctr) | Received at Relay | Confirm buzz | Error each press (m) | Average | Worst | Signal (dBm) | SNR (dB) |
|---|---|---|---|---|---|---|---|---|
| Quad | 178 to 182 | 5 of 5 | 5 of 5 | 5.46, 5.28, 4.89, 5.40, 4.39 | 5.1 m | 5.5 m | -100 to -82 | 4.25 to 10.0 |
| Sidewalk by the Sentinel Center (gym) | 183 to 187 | 5 of 5 | 5 of 5 | 1.89, 1.26, 1.00, 0.96, 0.96 | 1.2 m | 1.9 m | -83 to -80 | 9.5 to 10.25 |
| Soccer field | 188 to 192 | 5 of 5 | 5 of 5 | 1.19, 1.11, 1.01, 0.91, 1.11 | 1.1 m | 1.2 m | -90 to -88 | 9.0 to 9.75 |
| **All** | **15** | **15 of 15** | **15 of 15** | | **2.4 m** (median 1.2 m) | **5.5 m** | | |

- **Error method:** haversine distance between the Fob's reported lat/lon and the Maps pin.
- **Reported accuracy:** the Fob reported 2 to 4 m on every press.
- **Delivery:** 15 of 15 presses reached the Relay, and every one gave the confirm buzz (two pulses). No losses, no duplicates.

## Compared with run 1 (Nov 9, practice)

| Spot | Run 1 average | Run 2 average |
|---|---|---|
| Quad | 5.6 m | 5.1 m |
| Sidewalk | 1.2 m | 1.2 m |
| Soccer field | 0.7 m | 1.1 m |
| All | 2.5 m | 2.4 m |

The two runs agree closely. **The Quad is about 5 m off both days, always in the same direction** (the Fob reports a spot slightly northwest of the pin). An error that is the same size and direction on two different days is more likely a fixed cause than random GPS noise. Two likely explanations:
- The pin is not exactly where the Fob was held.
- Nearby buildings reflect the satellite signals (multipath).

A quick check next time: drop a fresh pin while standing on the mark, and compare.

## Notes

- **ctr 177** (14:30, -22 dBm) was pressed next to the Relay before going out, with no GPS fix. It is not part of the test.
- **The courts were not tested** (they were busy). The run 1 courts result (2 presses lost) is still open. Retest it when the courts are free, as a coverage point.
- **5 non-SafePing packets** were heard during the run, more than the usual one about every 10 minutes. This is other devices on the same band. None of them interfered with an alert.
- **Weakest link:** the Quad, at -100 dBm and SNR 4.25 on ctr 179. It was still received and confirmed, but it is the closest to the edge.
- **Limitation:** only 5 presses per spot, and 3 spots. The result is strong for these spots, not for the whole campus.

## Files

In the run folder:
- `*_raw.txt`, `*_alerts.csv`, `*_summary.txt` (logger)
- `dt10_page.csv` (phone page, 15 rows, all "confirm")
