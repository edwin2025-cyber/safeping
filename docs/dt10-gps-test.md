# DT-10 GPS accuracy test (run 2, the official run)

**Pass criterion:** the reported location is within **10 m** of the true spot for at least **95%** of outdoor presses with a GPS fix.
- The criterion was set on Nov 9, before this run.
- Run 1 (Nov 9) was a practice run.

**Goal:** At 4 outdoor spots, press the Fob 5 times each (20 presses). Compare where the Fob says it is with where it really is.

**Who:** Edwin at the third-floor window with the laptop and the Relay. Partners walk the Fob and a phone.

## What changed from run 1

1. **Press type: SUSPICIOUS (2 quick presses), not STATUS.**
   - STATUS gives only one short buzz, with no confirm or fail result, so partners could not tell whether a press got through.
   - SUSPICIOUS gives the result buzz.
   - Nothing gets texted, because only the logger runs (no server).
2. **True locations are known before the test.** The `dt10.html` page has them preset, so partners do not need to paste anything.
3. **Courts added** as a fourth spot. In run 1, the 2 presses there never reached the Relay.
4. **30 seconds between presses** (not 10), so the GPS solves a fresh position more often. Each press is a better sample.
5. **Every press is logged on the page**, including what the Fob buzzed.

## 1. Before going out

1. Charge the LiPo while you are awake. Unplug it from the charger when it is done.
2. Check the phone page has the 4 spots with their true locations (see the range-logger update).
3. The 4 spots, with true locations (Google Maps satellite pins):

| # | Spot | True lat, lon | Stand on |
|---|---|---|---|
| 1 | Quad | 34.7255497, -86.6552746 | the same mark as the pin |
| 2 | Sidewalk by the Sentinel Center (gym) | 34.7252069, -86.6547724 | the same mark as the pin |
| 3 | Soccer field | 34.7235808, -86.6539513 | the center dot |
| 4 | Courts | 34.7243290, -86.6539111 | the same mark as the pin |

   Before going out, look at each pin on satellite view so the partners know exactly where to stand.

## 2. Setup at the window

1. Do NOT run the server or the serial bridge. The logger needs COM14 to itself.
2. Plug the Relay into the laptop (COM14). Point the antenna out the window. Note which direction the window faces.
3. Start the logger. Run these as two separate lines:
   ```
   cd $HOME\Documents\safeping
   ```
   ```
   python tests\field_log.py --label dt10_run2 --no-fob
   ```
   The startup line should say "Fob not logged (--no-fob)".
4. Connect the LiPo to the Fob. Partners take it outside.
5. Partners wait **2 minutes in open sky** before the first press.

## 3. At each spot

1. Stand exactly on the mark.
2. On the page, tap the spot. Its true location is already filled in.
3. **Press the Fob twice quickly** (SUSPICIOUS).
4. Wait for the result buzz, then tap the matching button on the page:
   - **Confirm buzz** (two short pulses)
   - **Fail buzz** (one long buzz)
   - **No result buzz** (only the press buzz)
5. Wait **30 seconds**, then do the next press. Do 5 presses at each spot.
6. Text Edwin "Spot N done".
7. At the window, Edwin checks that 5 alerts arrived with a "GPS ..., ... acc ... m" line each, and texts back the count.

Order: Quad, Sidewalk, Soccer field, Courts. About 4 minutes per spot.

## 4. After

1. Stop the logger with Ctrl+C.
2. Unplug the LiPo from the Fob.
3. Partners tap **Export CSV** on the page and send it to Edwin.
4. Put the page's CSV in the logger's run folder as `dt10_page.csv`.
5. Send Claude the run folder.
6. Results to compute:
   - For each press with a GPS fix: the error in meters vs. the true location.
   - The percent within 10 m (pass if 95% or more).
   - The average and the worst case.
   - Presses lost (sent on the page but not received by the Relay), per spot.
