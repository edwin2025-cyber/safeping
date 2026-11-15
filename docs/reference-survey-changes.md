# Reference board and floor survey: changes (2026-11-14)

Goal: collect the data to tell which building and floor a Fob is on, with no new parts. This adds the tools only. No floor or building is worked out yet. That comes from the survey data.

Nothing here has run on a board yet. Everything below was tested on the laptop with the real firmware on a fake board and the real server code.

## 1. What changed, by file

### Message format (changed first)

| File | Change |
|---|---|
| `docs/message-format.md` | New topics `safeping/ref/<id>` (QoS 0) and `safeping/survey/<id>` (QoS 1). New broker user `safeping-ref`. New fields `pd` (pressure in tenths of a pascal), `n`, `fw` on REF, and `fix`, `sats`, `aps` on SURVEY. Signing strings for both. SURVEY skips the counter window. SURVEY may be up to 2048 bytes (WiFi only). New sections "Reference readings (REF)" and "Survey points (SURVEY)". |

Why `pd`: the message format only allows whole numbers (floats break the signature). "Pa with 1 decimal" is sent as tenths of a pascal: `988124` is 98812.4 Pa. `p` stays as whole pascals, so the old code still works.

### Firmware, shared (`firmware/lib/`)

| File | Change |
|---|---|
| `msgsign.py` | New. The signing string and signature for every message type. Used by the Fob and the Reference board (the Fob's own copy in `main.py` was removed). |
| `baro.py` | New. Average pressure over a window, to one decimal, and the time of the window's middle. Used by both boards. |
| `survey.py` | New. Survey mode: WiFi scan to the `aps` list, the SURVEY message, the `SURVEY_POINT` log line, and the store for points waiting for WiFi (one file per point in `survey_q/`, written through a `.tmp` file). |
| `bme280.py` | New `read_q8()`: one reading with the fraction kept (pascals times 256). `read()` gives exactly the same numbers as before (checked on 10,000 random readings). |
| `sendpath.py` | New `tls_context()`: the CA loading that was in the Fob's `main.py`, now shared with the Reference board. |
| `selfcheck.py` | `summary_line()` takes an optional list of checks, so the Reference board prints its own `SELF_CHECK` line. The Fob's line is unchanged. |

### Firmware, Reference board (`firmware/ref/`, new)

| File | Change |
|---|---|
| `main.py` | New. Reads the sensor every 2 s, publishes a signed REF every 30 s, reconnects by itself, watchdog on, LED, crash-safe counter. Version `ref-2026.11.14a`. |
| `config.example.py` | New. Its own device ID, key, WiFi and broker user. |
| `README.md` | New. What it does, the light, the log lines, the board file list. |
| `firmware/reference/README.md` | Note at the top: replaced by `firmware/ref/`. The old folder only held a first plan. You can `git rm` it. |

### Firmware, Fob

| File | Change |
|---|---|
| `firmware/fob/main.py` | Survey mode (`SURVEY_MODE`, off by default). A single press makes a survey point. Signing now comes from `msgsign.py`, TLS setup from `sendpath.tls_context()`. `wifi_send()` takes a topic. Version `2026.11.14b`. Every other behavior is unchanged (all old tests pass). |
| `firmware/fob/config.example.py` | `SURVEY_MODE` and `SURVEY_AUTO_MS`, plus the other survey settings in the comment. |

### Server

| File | Change |
|---|---|
| `server/validate.py` | SURVEY type. REF and SURVEY signing strings. Checks for `pd`, `n`, `fw`, `fix`, `sats`, `aps`. 2048 byte limit for SURVEY only. SURVEY counter rule without the window. |
| `server/db.py` | New table `survey_points`. New columns: `reference_readings` gets `device_id`, `device_ts`, `pressure_dpa`, `samples`, `firmware`, `ref_time`. `alerts` gets `ref_pressure`, `ref_diff`, `ref_offset`. Added on start, old rows kept. |
| `server/refmatch.py` | New. The reference pressure at a given time (interpolated within 60 s), the Fob's sensor offset from `sensor_offsets.json`, and pressure difference to meters. |
| `server/processor.py` | Stores REF with the new fields. Stores and acks SURVEY (never an alert, text or Pushover). Each alert with pressure stores the reference at its press time and the difference. Readings older than 14 days are deleted (hourly). |
| `server/mqtt_listener.py` | Subscribes to `safeping/ref/+` (QoS 0, never acked) and `safeping/survey/+` (QoS 1, acked). |
| `server/app.py` | `/api/status` has the pressure to one decimal, temperature and board ID. `/api/devices` has the Reference board's last reading. `/api/alerts` has the reference fields. New `/api/reference` and `/api/survey`. |
| `server/config.py` | New settings: `REF_KEEP_DAYS` (14), `REF_MATCH_S` (60), `SAFEPING_SENSOR_OFFSETS` (default `server/sensor_offsets.json`), the two topics and the SURVEY size limit. |

### Dashboard

| File | Change |
|---|---|
| `TopBar.jsx` | Reference: green "updated 20 s ago" when a reading arrived in the last 2 minutes, orange otherwise. |
| `DevicesPage.jsx`, `live.css` | The Reference board has its own table under the Fobs: last reading, pressure, temperature, readings. |
| `DevicePeek.jsx` | Reference board panel: a Last reading card instead of the old Role card. |
| `AlertPeek.jsx` | Reference and Difference rows under Pressure ("-52.3 Pa, about 4.5 m above the reference"). |
| `lib/format.js` | `formatPa`, `formatPaDiff`, `heightText`. |
| `mock/data.js`, `mock/api.js` | Mock Reference board (`MOCK-REF-001`), a reading age that counts up, reference fields on mock alerts, one calibrated mock Fob. |
| `docs/dashboard.md` | The top bar, Devices, alert panel and API changes. |

### Tests and tools (laptop)

| File | Change |
|---|---|
| `tests/test_ref.py` | New. The Reference board firmware on a fake board, checked against the server. |
| `tests/test_survey.py` | New. Survey mode on the real Fob firmware, checked against the server. |
| `server/test_reference.py` | New. Reference matching on alerts, offsets, API, 14-day delete. |
| `tests/test_survey_analyze.py` | New. Both analysis scripts on fake data with known answers. |
| `tests/ref_calibrate.py` | New. Part 5 calibration. |
| `tests/survey_analyze.py` | New. Part 5 analysis. Writes `docs/survey-results.md`. |
| `tests/surveydata.py` | New. Shared by the two scripts: loading from the API or files, reference interpolation. |
| `tests/field_log.py` | Knows the `SURVEY_POINT` and `SURVEY_SENT` lines and counts survey points in the summary. Survey points are never counted as alerts. |
| `tests/test_imports.py` | Also checks `firmware/ref`. |
| `docs/survey-results.md` | Placeholder until the script runs. |

### Phone page (`range-logger` repo, next to this one)

| File | Change |
|---|---|
| `survey.html` | New. Same style as `dt10.html`. Pick building and floor, type a spot (or tap "one end", "middle", "other end"), tap Mark point. Running list, undo last, copy or download CSV, keep screen on, 2 s tap guard. Saved on the phone. |
| `survey-sw.js` | New. Keeps an offline copy of `survey.html` and its font after the first load. |
| `index.html` | Link to the survey page. |

## 2. Test results

All on the laptop (Python 3.13, the real firmware files on `tests/fakeboard.py`, the real server code on a throwaway database). Every script, old and new:

| Script | Result |
|---|---|
| `tests/test_ref.py` (new) | 63 of 63 |
| `tests/test_survey.py` (new) | 83 of 83 |
| `tests/test_survey_analyze.py` (new) | 54 of 54 |
| `server/test_reference.py` (new) | 27 of 27 |
| `tests/test_counter.py` | 22 of 22 |
| `tests/test_help.py` | 51 of 51 |
| `tests/test_imports.py` | 32 of 32 (now includes `firmware/ref` and the new lib files) |
| `tests/test_led.py` | 30 of 30 |
| `tests/test_press_record.py` | 55 of 55 |
| `tests/test_retry_queue.py` | 71 of 71 |
| `tests/test_selfcheck.py` | 57 of 57 |
| `tests/test_sendpath.py` | 37 of 37 |
| `tests/test_wifi_errors.py` | 58 of 58 |
| `server/test_attacks.py` | 19 of 19 |
| `server/test_duplicates.py` | 58 of 58 |
| `server/test_pushover.py` | 81 of 81 |
| `server/test_serial_bridge.py` | 17 of 17 |

What the new tests cover:

- **Signing**: the Fob, the Reference board and the server build the same signing string for REF and SURVEY. The server accepts their messages and rejects forged ones, a REF from a Fob, a SURVEY from the Reference board, and REF or SURVEY messages with bad fields.
- **REF**: 15 readings per 30 s, pressure to one decimal, the middle-of-window time, the counter saved in blocks and never reused after a restart. Broker drop, WiFi drop, a dead connection (ping) and a failed sensor: right light, no counter used for nothing, reconnects with a growing wait (5, 10, 20 s), back to 5 s after it connects.
- **SURVEY**: one press makes a point on `safeping/survey/<id>`, never LoRa, never an alert, never Pushover. Two presses are still a SUSPICIOUS alert. Survey mode off: one press is STATUS. No WiFi: the point is kept in `survey_q/`, survives a restart, is sent later oldest first, and a press stops that send. Store full: orange. The biggest point (15 access points with 32-byte names) is under 2048 bytes. A point far below the newest counter is still accepted, a copy is a duplicate and acked again.
- **Alerts and the reference**: interpolated between two readings, nearest within 60 s, none beyond. The sensor offset from `sensor_offsets.json`. A broken offsets file never stops an alert. The old floor rule gives the same result as before.
- **Analysis on fake data**: a made-up walk with known floor heights, 40 Pa of weather drift, a Fob reading 3.0 Pa high and sensor noise. `ref_calibrate.py` finds the offset (3.0 Pa within 0.3), warns on too few pairs, a big spread, or drift, and keeps other Fobs' offsets in the file. `survey_analyze.py` gets every floor's height back within 0.3 m, finds the gaps (Academic 1 to 2: about 3.9 m), calls 3.5 m floors apart and 0.2 m floors not apart, gets the building from WiFi right, and lists the mark with no point, the point with no mark and the pair 90 s apart.
- **Phone page**: driven once with a small fake page in Node (not on a phone): building and floor buttons, the quick spot names, the tap guard, undo, reload from phone storage, and the CSV (a spot with a comma and quotes is quoted). `survey_analyze.py` reads that CSV correctly.
- **Dashboard**: builds in normal and mock mode. I did not look at it in a browser.

## 3. Copy lists and config lines

Everything goes to the top level `/` on the board, not `/lib`.

### Reference board (new board)

| Board path | From |
|---|---|
| `/main.py` | `firmware/ref/main.py` |
| `/config.py` | your copy of `firmware/ref/config.example.py`, filled in (see below) |
| `/msgsign.py` | `firmware/lib/msgsign.py` |
| `/ackcheck.py` | `firmware/lib/ackcheck.py` |
| `/sendpath.py` | `firmware/lib/sendpath.py` |
| `/selfcheck.py` | `firmware/lib/selfcheck.py` |
| `/counterfile.py` | `firmware/lib/counterfile.py` |
| `/umqtt_safe.py` | `firmware/lib/umqtt_safe.py` |
| `/bme280.py` | `firmware/lib/bme280.py` |
| `/baro.py` | `firmware/lib/baro.py` |
| `/certs/broker-ca.pem` | the same CA file the Fob has |

Reference board `config.py` (all lines are in `config.example.py`):

```python
DEVICE_ID = "REF-001"
SECRET_KEY = "paste-the-key-from-add_device.py"
WIFI_SSID = "the school WiFi name"
WIFI_PASSWORD = "the school WiFi password"
MQTT_HOST = "your-deployment-address"      # same as the Fob
MQTT_PORT = 8883
MQTT_USER = "safeping-ref"
MQTT_PASSWORD = "the-ref-broker-password"  # the new EMQX user's password
MQTT_TLS = True
MQTT_CA_FILE = "/certs/broker-ca.pem"
WATCHDOG_ENABLED = False                   # False while you copy files, then True
```

### Fob

| Board path | From | Why |
|---|---|---|
| `/main.py` | `firmware/fob/main.py` | survey mode |
| `/msgsign.py` | `firmware/lib/msgsign.py` | new, **required** (the Fob will not start without it) |
| `/sendpath.py` | `firmware/lib/sendpath.py` | changed, **required** (`main.py` calls the new `tls_context()`) |
| `/survey.py` | `firmware/lib/survey.py` | new, survey mode |
| `/baro.py` | `firmware/lib/baro.py` | new, survey mode |
| `/bme280.py` | `firmware/lib/bme280.py` | changed, gives the decimal |
| `/selfcheck.py` | `firmware/lib/selfcheck.py` | changed (the Fob's line is the same) |

Lines to add by hand to the Fob's `config.py`:

```python
SURVEY_MODE = True       # for the calibration and the walk. False for normal use.
SURVEY_AUTO_MS = 30000   # only during the 10 minute calibration. 0 for the walk.
```

### Server

- No new packages.
- Optional settings (environment variables), with their defaults: `REF_KEEP_DAYS=14`, `REF_MATCH_S=60`, `SAFEPING_SENSOR_OFFSETS=server/sensor_offsets.json`. Nothing to set for the defaults.
- Restart `python server/app.py` once. It adds the new table and columns.

## 4. EMQX changes

In the EMQX Cloud console for the deployment (names can differ a little in the console):

1. **Access Control > Authentication**: add a user.
   - Username: `safeping-ref`
   - Password: a new strong one. It goes only in the Reference board's `config.py`.
2. **Access Control > Authorization**: add rules for `safeping-ref`, the allow rule above the deny rule:

   | Username | Topic | Action | Permission |
   |---|---|---|---|
   | `safeping-ref` | `safeping/ref/#` | Publish | Allow |
   | `safeping-ref` | `#` | Publish and Subscribe | Deny |

3. **Server user** `safeping-server`: allow it to subscribe to the two new topics (if its rules list topics one by one):

   | Username | Topic | Action | Permission |
   |---|---|---|---|
   | `safeping-server` | `safeping/ref/#` | Subscribe | Allow |
   | `safeping-server` | `safeping/survey/#` | Subscribe | Allow |

4. **Fob user** `safeping-fob`: the survey points need one more rule (if its rules list topics one by one):

   | Username | Topic | Action | Permission |
   |---|---|---|---|
   | `safeping-fob` | `safeping/survey/#` | Publish | Allow |

   Without it, a survey point is refused by the broker. The Fob keeps it in flash and tries again every 30 s, so nothing is lost, but nothing reaches the server.

If your rules for `safeping-server` and `safeping-fob` already allow `safeping/#`, steps 3 and 4 need nothing.

## 5. Your plan

### A. Laptop, before anything else (15 minutes)

1. Restart the server: `python server/app.py`.
2. Register the Reference board: `python server/add_device.py REF-001 --role REF`. It prints the key. Keep the window open.
3. Make the EMQX changes in section 4.

### B. Flash MicroPython on the second board (15 minutes)

1. On the Fob, in the Thonny shell, run `import os; os.uname()`. Write down the version and the machine line. Use the **same MicroPython file** for the second board, so both boards run the same code (the Fob runs 1.27.0, see `docs/features-changes.md` section 8 about newer versions).
2. Plug in the second board. In Thonny: Tools > Options > Interpreter > MicroPython (ESP32) > "Install or update MicroPython (esptool)". Pick the board's COM port and that same file. Tick "Erase all flash before installing". Install.
3. If Thonny cannot find the board: hold BOOT, press and release RST, then release BOOT, and try again.
4. When it is done, press RST. The Thonny shell shows the MicroPython banner. `os.uname()` should match the Fob.

### C. First boot of the Reference board (20 minutes, on your desk)

1. Plug the pressure sensor into the board's Qwiic port.
2. In Thonny, make a folder `certs` on the board and copy the CA file into it.
3. Copy every file in the Reference board list (section 3) to `/`. Fill in `config.py` with the key from step A2, the school WiFi and the `safeping-ref` password. Keep `WATCHDOG_ENABLED = False` for now.
4. Press RST and watch the shell. You should see, in this order:
   - `Sensor: BME280 (chip id 0x60) at 0x77` (or `BMP280`, or `at 0x76`). If it says `Sensor: off`, stop and tell me what chip it is.
   - `SELF_CHECK key=ok counter=new pressure=ok wifi=ok ...`
   - `broker connected: ...`
   - `REF_SENT ctr=0 p=98812.4 t=21.50 n=15 ts=...` 30 s later, then every 30 s.
5. Check the dashboard: the top bar Reference is green with "updated ... s ago", and Devices shows the Reference board with its pressure.
6. Set `WATCHDOG_ENABLED = True` in `config.py`, save, press RST, and check the shell says `watchdog on`.
7. Take it to academic building floor 1 and plug it into USB wall power. Pick a spot away from doors, vents, heaters and sun, at about desk height, where it can stay for weeks. Write down the spot. In about a minute the dashboard top bar should be green again.

The light on the Reference board: off is good. A short green blink every 30 s is a reading sent. Blue blinking is no WiFi. Steady orange is the sensor or the broker.

### D. Update the Fob (10 minutes)

1. Copy the Fob files in section 3. Add the two lines to `config.py` (`SURVEY_MODE = True`, `SURVEY_AUTO_MS = 30000`).
2. Press RST somewhere with WiFi, so the clock gets set. After the self-check light you should see a **long blue blink** (2 s): survey mode is on.

### E. The 10 minute calibration (15 minutes, at the Reference board)

1. Put the Fob next to the Reference board, on the same surface, at the same height. Do not hold it. Wait 5 minutes so its temperature settles.
2. The Fob makes a survey point every 30 s by itself (two short green blinks each time). Leave it for 10 minutes (20 points).
3. On the laptop with the server: `python tests/ref_calibrate.py --device FOB-001`
   - Look for `pairs: 18` or more, `spread` under 2 Pa, and no WARNING lines.
   - It saves the offset to `server/sensor_offsets.json`. The server uses it from the next alert, no restart.
   - If it warns, fix what it says and run it again. `--dry-run` prints without saving.
4. Set `SURVEY_AUTO_MS = 0` in the Fob's `config.py`, save, and press RST (long blue blink again).

### F. The survey walk (45 to 60 minutes)

Before you leave:

1. On the phone, open `survey.html` on GitHub Pages once with a signal. It says "Works offline". Tap Clear all if old points are there. Turn on "Keep screen on".
2. Check the phone and laptop clocks are right (they are matched within 60 s).

The route: all floors of all three buildings, bottom to top in each, 3 points per floor (one end of the main hallway, the middle, the other end).

| Building | Floors | Points |
|---|---|---|
| Academic (start here, near the Reference board) | 1, 2, 3 | 9 |
| Residential | 0, 1, 2, 3 | 12 |
| Sentinel Center | 0, 1, 2 | 9 |

Also take one extra point right next to the Reference board at the start and one at the end (mark them as Academic floor 1, "next to reference"). They should both come out near 0 m and show if anything drifted.

At each spot:

1. Stand still. Hold the Fob the same way every time (for example in your hand at waist height). 1 m of height is about 12 Pa, so this matters.
2. Press the Fob once. Right away, tap **Mark point** on the phone.
3. Do not move until the Fob gives **two short green blinks** (about 5 to 10 s: 3 s of pressure, the WiFi scan, then the send). That means it was sent or saved.
4. Orange and a long buzz means the point was not kept. Tap Undo last on the phone, then press and mark again.

Places with no WiFi are fine: the points wait in the Fob and go out later. At the end, stay somewhere with WiFi for 3 minutes so every waiting point is sent.

After the walk:

1. On the phone, tap Download CSV (or Copy CSV) and put the file on the laptop.
2. Run: `python tests/survey_analyze.py --phone survey_2026-11-15_1400.csv --device FOB-001` (your file name).
3. It prints the results and writes `docs/survey-results.md`. Check "Not matched" at the bottom: a mark with no point usually means the point never reached the server, or the phone and Fob clocks are off.
4. Set `SURVEY_MODE = False` on the Fob for normal use and press RST.

## 6. What I guessed or could not do

1. **The Reference board's sensor.** I assumed the same BME280 on Qwiic as the Fob, on I2C SDA 23 and SCL 24. The code also accepts a BMP280 and tries address 0x77, then 0x76. I could not check the part. Please confirm it, or tell me what `Sensor:` prints at the first boot.
2. **Nothing ran on a board.** Not tested on hardware: the WiFi scan on the ESP32-C5 (I assumed MicroPython's usual result order: name, BSSID, channel, signal, security, hidden), how long the scan takes on both bands, the NeoPixel on IO27 of the second board, and the real broker.
3. **The MicroPython file for the second board.** I do not know exactly which 1.27.0 file is on the Fob, so step B says to use the same one. I did not give an esptool command, because the flash offset for the ESP32-C5 depends on that file.
4. **EMQX.** I do not know your current rules for `safeping-fob` and `safeping-server`, so section 4 gives the rules to add if they list topics one by one. The console menu names may differ slightly.
5. **"Reference from the same minute"** is the two readings around the press time, interpolated, when both are within 60 s. Otherwise the nearest within 60 s, otherwise none. The time used is the alert's `ts` (when the Fob read the pressure), or the arrival time without `ts`.
6. **"Pa with 1 decimal"** is sent as whole tenths of a pascal (`pd`), because floats would break the signature. `p` (whole pascals) is still sent.
7. **The REF counter is saved in blocks of 20** (one flash write every 10 minutes, not every 30 s). It uses the Fob's method for the write itself (`.tmp` file, then rename), and a restart starts above the saved number, so a counter is never reused. The Fob's RTC copy and boot jump are not needed for this.
8. **The Reference board's light.** Blue blinking whenever WiFi is down (joining or waiting to try again), not only during the join, so a WiFi problem never looks like a broker problem.
9. **`n=` in `SURVEY_POINT`** is the point number since boot. The readings in the average are `samples=`.
10. **Survey feedback** is the two short green blinks only, no buzz, as written. A point that is not kept gets orange and the long buzz.
11. **Added, not asked:** `SURVEY_AUTO_MS` (points by themselves) for the calibration, so you do not have to press 20 times. The extra start and end points next to the Reference board in the plan.
12. **SURVEY skips the counter window** on the server, so a long walk without WiFi never loses points. Alerts keep the window.
13. **A survey point needs a set clock.** If the Fob had no WiFi since power on, the point has no `ts` and the server can only use its arrival time, which may be far off. Start the Fob somewhere with WiFi.
14. **During a survey point** (5 to 10 s) a press waits until it finishes. A survey point also closes the "help is coming" listening of an earlier alert (one connection at a time). Survey mode is for the walk only.
15. **The old floor rule** (`PA_PER_FLOOR`, latest reading) still runs unchanged. No new floor logic was added.
16. **One Reference board.** With two boards, the server would mix their readings when matching. Fine for now.
17. **The phone page** was tested with a fake page in Node, not on a real phone, and the offline copy needs one load with a signal. It lives in the `range-logger` repo, which you commit separately.
18. **The dashboard** builds in both modes, but I did not look at it in a browser.
19. **Heights in meters** use the standard height formula with the reference temperature (about 11.5 Pa per meter at our pressure). Heights are above the Reference board itself, so the board's own height on its desk is part of every number.
