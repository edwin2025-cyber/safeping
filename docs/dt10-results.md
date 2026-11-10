# DT-10 GPS accuracy test: results (run 1, practice)

**Date:** Nov 9, 2026, 14:44 to 15:08
**Run folder:** `logs/2026-11-09/144423_dt10_gps/`
**Setup:**
- The Relay was at the third-floor window, on COM14, with `field_log.py --label dt10_gps --no-fob`.
- The Fob ran on LiPo.
- Partners recorded each press on the `dt10.html` phone page.

**True location:** a Google Maps satellite pin for each spot, taken right after the test. The phone GPS readings on the page were not used as truth: one reported 27 m accuracy, which is worse than the Fob.

## Results

| Spot | Presses (ctr) | Received at Relay | Fob error vs. pin, each press (m) | Average | Worst |
|---|---|---|---|---|---|
| Quad | 156 to 160 | 5 of 5 | 5.81, 5.54, 5.54, 5.48, 5.48 | 5.6 m | 5.8 m |
| Sidewalk by the Sentinel Center (gym) | 161 to 165 | 5 of 5 | 1.21, 1.21, 1.26, 1.26, 1.26 | 1.2 m | 1.3 m |
| Soccer field | 166 to 170 | 5 of 5 | 0.74, 0.74, 0.74, 0.74, 0.74 | 0.7 m | 0.7 m |
| **All** | **15** | **15 of 15** (all confirmed on the page) | | **2.5 m** (median 1.3 m) | **5.8 m** |

- **Error method:** haversine distance between the Fob's reported lat/lon and the Maps pin.
- **Reported accuracy:** the Fob reported 3 to 4 m on every press. The Quad error (5.6 m) was a bit above that, likely because of nearby trees or buildings. The open spots were well inside it.
- **Signal at the spots:** -79 to -95 dBm, SNR 5.0 to 10.0 dB. Across the whole run: average -82 dBm, SNR 8.75 dB.
- **Pass criterion** (set after this run, so this run is practice): within 10 m for at least 95% of outdoor presses with a GPS fix. Run 1 met it: 15 of 15 presses (100%) were within 10 m. Run 2 is the official test.

## Notes

- **ctr 155** (14:45, SUSPICIOUS) had no GPS position. It was pressed before going outside, so that is expected.
- **ctr 171 and 172** were most likely pressed at the **courts** (Maps pin 34.7243290, -86.6539111). They were not logged on the phone page. **Neither reached the Relay**, and neither is in the Relay's `queue.txt` (checked Nov 9). The partners remember a normal buzz, but a confirm buzz needs a signed ack from the Relay, so the buzz was most likely the one long buzz (not confirmed). That is odd, because the soccer field worked 5 of 5 even though it is farther out (about 250 m from the quad pin, against about 185 m for the courts). It suggests something blocks the line of sight between the courts and the Relay window (a building, a fence or terrain), not plain distance. The courts should be retested with logging, as a range and coverage point. ctr 173 was received at 15:07 next to the Relay (-30 dBm).
- **1 non-SafePing packet** was heard at 15:06. This matches the interference seen before (about one every 10 minutes).
- **The parking lot was not reachable**, so spot 2 was moved to the sidewalk by the Sentinel Center (gym). It was logged under the "Parking lot" button on the page.
- **Finding: STATUS presses give no delivery feedback.** A STATUS press gives one short buzz when pressed, and no confirm or fail buzz afterward. That means the "confirmed" taps for the STATUS presses on the phone page were not based on a real confirm. The Relay log is the ground truth for this run. Run 2 uses SUSPICIOUS presses, which give the result buzz. A firmware change to give STATUS a result buzz (at least on failure) is on the list.
- **Spots 2 and 3 used mixed press types** (STATUS, SUSPICIOUS, MEDICAL, SILENT), not only STATUS. GPS works the same for every type.
- **Limitation:** the Fob reported almost the same position for all 5 presses at each spot, so the presses are not fully independent samples. A second run on a different day or time would strengthen the result.

## Files

In the run folder:
- `*_raw.txt`, `*_alerts.csv`, `*_summary.txt` (logger)
- `dt10_page.csv` (phone page)
- `true_locations.txt` (Maps pins)
