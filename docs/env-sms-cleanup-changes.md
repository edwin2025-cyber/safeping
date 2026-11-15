# Settings file, real SMS and cleanup: changes (2026-11-15)

Nothing here has run on a board or against the real Textbelt or broker yet. Everything was tested on the laptop: the real firmware on the fake board, the real server code on a throwaway database, and a fake Textbelt on 127.0.0.1.

## 1. What changed, by file

### Part 1. Settings file

| File | Change |
|---|---|
| `server/envfile.py` | New. One shared loader for `safeping.env`: `SAFEPING_ENV_FILE`, else `Documents\safeping-private\safeping.env`. Spaces around `=`, blank lines, `#` comment lines, quotes, `export`, and the hidden marker Notepad adds (BOM). The environment wins over the file. A file inside the repo folder is refused with a clear message. Prints only names, never values. A missing file changes nothing. |
| `server/app.py`, `server/serial_bridge.py`, `server/mqtt_listener.py`, `server/fake_fob.py` | Load the file first, only when run as a program (`if __name__ == "__main__"`), so the tests that import them never read your real file. |
| `tests/field_log.py`, `tests/broker_check.py`, `tests/ref_calibrate.py`, `tests/survey_analyze.py` | Load the file when they run. `tests/surveydata.py` has the shared `load_settings()` for the last two. |
| `.gitignore` | `*.env` and `*.env.*` ignored everywhere. |
| `docs/how-to-run.md` | New section 0: make `safeping.env` once, with the full template. The `$env:` blocks in sections 1, 8 and 9 are gone. A short note says `$env:` still works and wins. |
| `README.md` | Settings table: the file, and the Textbelt names instead of Twilio. |

### Part 2. Real SMS through Textbelt

| File | Change |
|---|---|
| `server/textbelt.py` | New. Replaces the dry run in `notify.py`. Modes `off`, `dry` (default), `live`. POST to `https://textbelt.com/text` (fixed in code) with `phone`, `message`, `sender=SafePing`, `key`. MEDICAL, SUSPICIOUS and SILENT only. One text per alert per number, at most `SAFEPING_SMS_MAX_PER_HOUR` (20) per hour, logged when the cap is hit. "Reply STOP to opt out" only on a number's first text. Under 160 characters, plain characters only. Stores each `textId` and the last `quotaRemaining`. Never prints the key. Numbers only as their last 2 digits. Never raises. |
| `server/processor.py` | Pushover first, then the text, after the alert is saved and acked. `notify.py` is no longer used. |
| `server/config.py` | `SAFEPING_SMS`, `TEXTBELT_KEY`, `SAFEPING_SMS_TO`, `SAFEPING_SMS_MAX_PER_HOUR`. Twilio settings removed. Also `SAFEPING_FAKEFOB_MQTT_USER` and `_PASS`. |
| `server/db.py` | New tables `sms_sent` (one row per alert and number: a hash of the number, its last 2 digits, the textId, the error, the quota) and `sms_numbers` (numbers that had a text, as hashes). `notify_status` gets a `quota` column. |
| `server/app.py` | `/api/stats` has `sms` (Settings > Health). `[SMS] ...` start line. |
| `server/serial_bridge.py`, `server/mqtt_listener.py` | `[SMS] ...` start line. Texts go out from both, like Pushover. |
| `dashboard/src/components/SettingsModal.jsx` | Health row "Text messages": mode, last send, credits left, last error. Orange under 25 credits, or when the newest text failed, or the key or numbers are missing. |
| `dashboard/src/mock/api.js`, `dashboard/src/lib/preview.js` | The `sms` block in mock mode (live, 18 credits, so orange) and in the empty preview (dry). |
| `docs/how-to-run.md` section 10, `docs/dashboard.md` | How to use it, the Health row. |

### Part 3. Fixes

| Item | Files | Change |
|---|---|---|
| 1. Broker lockdown | `server/fake_fob.py`, `server/config.py` | Publishes to `safeping/alert/<id>` (REF: `safeping/ref/<id>`) with its own login `SAFEPING_FAKEFOB_MQTT_USER` and `_PASS`. Subscribes to `safeping/ack/<id>` first and prints the server's ack, so it is a real end-to-end check. Says so if no PUBACK or no ack comes back. |
| 2. Old topics | `server/config.py`, `server/mqtt_listener.py`, `docs/message-format.md` | Comments say nothing sends on `safeping/alerts` or `safeping/reference` now. The server still subscribes (your call, see section 6). |
| 3. BOOT report retry | `firmware/lib/retryq.py`, `firmware/fob/main.py`, `docs/message-format.md` | A BOOT report not confirmed on both paths (at boot, or sent later after a press) goes in the retry queue as the lowest kind: dropped first when full, tried after every alert, no light or buzz when it gets through. |
| 4. External NeoPixel | `firmware/fob/main.py`, `firmware/fob/config.example.py`, `docs/led-patterns.md`, `docs/hardware-connections.md` | `LED_PIN_EXTERNAL` (default None) and `LED_BRIGHTNESS_EXTERNAL` (default 30 percent). The second pixel shows exactly what IO27 shows. A pin the Fob already uses is refused with a WARNING. The wiring guide no longer says GPIO 2. |
| 5. Relay | none | Nothing changed. See section 8. |
| 6. MicroPython 1.29 | `firmware/lib/sendpath.py`, `firmware/lib/umqtt_safe.py`, `firmware/ref/main.py`, `firmware/fob/main.py`, `docs/how-to-run.md` section 11 | TLS errors given as text (`MBEDTLS_ERR_SSL_TIMEOUT`, since 1.28) are read correctly. The Reference board scans the I2C bus before picking the sensor. Both boards print the MicroPython version at boot. Upgrade steps for both boards. |
| 7. Reference sensor | `firmware/ref/main.py`, `firmware/lib/msgsign.py`, `server/validate.py`, `server/processor.py`, `server/db.py`, `server/app.py`, dashboard `DevicesPage.jsx`, `DevicePeek.jsx`, `live.css`, mock data, `docs/message-format.md`, `firmware/ref/README.md` | Auto-detect kept. A clear `SENSOR model=BME280 chip_id=0x60 address=0x77 i2c=0x36,0x77` line at boot. The board now sends a signed BOOT report with `sensor` (for example `BME280@0x77`) on its first broker connection. The server accepts BOOT from a Reference board and stores the sensor. The Devices page shows the board's Last start with the sensor. |

Firmware versions: Fob `2026.11.15a`, Reference board `ref-2026.11.15a`.

### Tests

| File | Change |
|---|---|
| `server/test_envfile.py` | New. Settings loader with fake files. |
| `server/test_textbelt.py` | New. Texts against a fake Textbelt. |
| `tests/test_cleanup.py` | New. BOOT retry, external LED, 1.29 TLS error text. |
| `tests/test_ref.py` | The BOOT report with the sensor, the I2C scan, the server side. |
| `server/test_reference.py`, `tests/test_survey.py`, `tests/test_survey_analyze.py` | Follow the moves (`textbelt` instead of `notify`, and the two analysis scripts never read the real settings file in a test). |

## 2. Test results

All 20 scripts, old and new, on the laptop:

| Script | Result |
|---|---|
| `server/test_envfile.py` (new) | 42 of 42 |
| `server/test_textbelt.py` (new) | 50 of 50 |
| `tests/test_cleanup.py` (new) | 38 of 38 |
| `tests/test_ref.py` | 78 of 78 (was 63) |
| `server/test_attacks.py` | 19 of 19 |
| `server/test_duplicates.py` | 58 of 58 |
| `server/test_pushover.py` | 81 of 81 |
| `server/test_reference.py` | 27 of 27 |
| `server/test_serial_bridge.py` | 17 of 17 |
| `tests/test_counter.py` | 22 of 22 |
| `tests/test_help.py` | 51 of 51 |
| `tests/test_imports.py` | 32 of 32 |
| `tests/test_led.py` | 30 of 30 |
| `tests/test_press_record.py` | 55 of 55 |
| `tests/test_retry_queue.py` | 71 of 71 |
| `tests/test_selfcheck.py` | 57 of 57 |
| `tests/test_sendpath.py` | 37 of 37 |
| `tests/test_survey.py` | 83 of 83 |
| `tests/test_survey_analyze.py` | 54 of 54 |
| `tests/test_wifi_errors.py` | 58 of 58 |

What the new tests cover:

- **Settings file:** comments, blank lines, spaces, both kinds of quotes, `export`, a value holding `=` and `#`, the BOM, a missing file, the environment winning, a file inside the repo refused, values never printed, skipped lines reported by number only. Importing the server programs does not read the file, and every program calls the loader. `git check-ignore` confirms `*.env` files are ignored. The test found one real bug, now fixed: a Windows short folder name (`EDWINN~1`) could slip past the inside-the-repo check.
- **Texts:** dry and off send nothing. Live: one request per number with phone, message, `sender=SafePing` and the key. The text format, under 160 characters, plain characters, "arrived late at", "Press time unknown". The STOP line on the first text only. Nothing for STATUS, BOOT, REF, SURVEY, a duplicate or a replay. One text per alert per number. The hourly cap, and its log line. A refused text, no connection, an HTTP error and a missing key never stop the alert, the ack or Pushover. textId and quota stored. Health orange at 12 credits. The serial bridge texts too. The key and the full numbers are never printed or stored.
- **BOOT retry:** queued when both paths fail, the same signed message, kept in `queue.json`, no light or buzz on success, also after a press stopped it. A queue full of alerts keeps the alerts.
- **External LED:** same colors and patterns at 30 percent, low battery dims both, off is off on both, the motor pin refused.
- **TLS error text:** number only, number and text, text only, for both timeout checks and the plain words.
- **Dashboard:** builds in normal and mock mode. Not looked at in a browser.

Example texts the code builds (numbers and names are placeholders):

```
SafePing MEDICAL: Student Name (FOB-001). Indoors, floor 2. Pressed 2:14 PM. Reply STOP to opt out
SafePing SILENT: Student Name (FOB-001). Place unknown. Pressed 2:14 PM, arrived late at 2:20 PM.
SafePing SUSPICIOUS: FOB-002. Place unknown. Press time unknown, received 2:14 PM.
```

## 3. The `safeping.env` template

Also in `docs/how-to-run.md` section 0. Placeholders only. Check your file has every name you use.

```
# SafePing settings. Real values only in Documents\safeping-private\safeping.env.

# ---- Cloud broker (EMQX), the server's login ----
SAFEPING_MQTT_HOST=your-deployment-address
SAFEPING_MQTT_PORT=8883
SAFEPING_MQTT_USER=safeping-server
SAFEPING_MQTT_PASS=the-server-broker-password
SAFEPING_MQTT_CA=C:\Users\YOU\Documents\safeping-private\the-ca-file.crt
# NO_MQTT=1                     (start the dashboard without the broker)

# ---- fake_fob.py over MQTT: the Fob's login ----
SAFEPING_FAKEFOB_MQTT_USER=safeping-fob
SAFEPING_FAKEFOB_MQTT_PASS=the-fob-broker-password

# ---- Dashboard ----
CARTO_KEY=the-carto-key
PA_PER_FLOOR=55
# DASHBOARD_PASSWORD=           (empty: no login)
# SAFEPING_PUBLIC_URL=http://the-laptop-address:5000   (link in Pushover)

# ---- Pushover ----
SAFEPING_PUSHOVER_USER=the-pushover-user-key
SAFEPING_PUSHOVER_TOKEN=the-pushover-app-token

# ---- Text messages (Textbelt) ----
# off, dry (print only, the default) or live
SAFEPING_SMS=dry
TEXTBELT_KEY=the-textbelt-key
# 10-digit numbers, comma separated
SAFEPING_SMS_TO=5550100001,5550100002
SAFEPING_SMS_MAX_PER_HOUR=20

# ---- Optional, defaults shown ----
# MAX_FLOOR=4
# REF_MAX_AGE_S=120
# REF_KEEP_DAYS=14
# REF_MATCH_S=60
# COUNTER_WINDOW=32
# MAX_ALERT_AGE_S=900
# SEEN_KEEP_DAYS=7
# SAFEPING_DB=                  (default server\safeping.db)
# SAFEPING_PLACES=              (default server\places.json)
# SAFEPING_SENSOR_OFFSETS=      (default server\sensor_offsets.json)
# SAFEPING_MQTT_CLIENT_ID=safeping-server
# HOST=0.0.0.0
# PORT=5000
```

`CARTO_KEY` is the key itself now (it was read from `carto_key.txt`). `SAFEPING_ENV_FILE` is not a line in the file: it is the one setting that says where the file is.

## 4. Copy lists

Everything at the top level `/`.

### Fob

| Board path | From | Why |
|---|---|---|
| `/main.py` | `firmware/fob/main.py` | BOOT retry, external LED, version line |
| `/retryq.py` | `firmware/lib/retryq.py` | BOOT is the lowest kind |
| `/sendpath.py` | `firmware/lib/sendpath.py` | TLS error text |
| `/umqtt_safe.py` | `firmware/lib/umqtt_safe.py` | TLS error text |
| `/msgsign.py` | `firmware/lib/msgsign.py` | BOOT with a sensor (the same file on both boards) |

If you have not copied the files from `docs/reference-survey-changes.md` yet, copy those too (`survey.py`, `baro.py`, `bme280.py`, `selfcheck.py`).

`config.py` lines to add by hand, only when the external pixel is wired (section 7):

```python
LED_PIN_EXTERNAL = 4         # the GPIO the pixel's data wire goes to
LED_BRIGHTNESS_EXTERNAL = 30 # percent of the board LED's brightness
```

### Relay

Nothing.

### Reference board

| Board path | From | Why |
|---|---|---|
| `/main.py` | `firmware/ref/main.py` | BOOT report with the sensor, I2C scan, version line |
| `/msgsign.py` | `firmware/lib/msgsign.py` | BOOT with a sensor |
| `/sendpath.py` | `firmware/lib/sendpath.py` | TLS error text |
| `/umqtt_safe.py` | `firmware/lib/umqtt_safe.py` | TLS error text |

The rest of the Reference board list in `firmware/ref/README.md` is unchanged. No new `config.py` lines.

## 5. `git rm` commands

```
git rm -r firmware/reference
git rm server/notify.py
```

- `firmware/reference/` only held the first plan. `firmware/ref/` replaced it.
- `server/notify.py` was the old SMS dry run. Nothing imports it any more (`textbelt.py` replaced it). The archived `firmware/archive/fob_sim_test_oct2026.py` mentions an `sms` result but does not import it.

## 6. EMQX: `safeping-ref`, and what the broker would refuse

Rule for the new user (whitelist, so nothing else is needed):

| Username | Topic | Action | Permission |
|---|---|---|---|
| `safeping-ref` | `safeping/ref/#` | Publish | Allow |

It covers the readings and the new BOOT report (both on `safeping/ref/REF-001`). The board subscribes to nothing. Its client id is its device id (`REF-001`). For a tighter rule, `safeping/ref/${clientid}` also works.

Every MQTT client in the repo against your rules:

| Client | Login | Does | Allowed? |
|---|---|---|---|
| Fob (`firmware/fob/main.py`, `sendpath.py`) | `safeping-fob` | publish `safeping/alert/<id>`, `safeping/survey/<id>`. Subscribe `safeping/ack/<id>`, `safeping/help/<id>` | yes |
| Reference board (`firmware/ref/main.py`) | `safeping-ref` | publish `safeping/ref/<id>` | yes, with the rule above |
| Server (`server/mqtt_listener.py`) | `safeping-server` | subscribe `safeping/alert/+`, `safeping/alerts`, `safeping/reference`, `safeping/ref/+`, `safeping/survey/+`. Publish `safeping/ack/<id>`, `safeping/help/<id>` | yes |
| `tests/broker_check.py` | `safeping-server` | publish and subscribe `safeping/test/broker_check` | yes |
| `server/fake_fob.py` before this change | `safeping-server` | publish `safeping/alerts` (and `safeping/reference` for REF) | **refused**. Fixed |
| `server/fake_fob.py` now | `SAFEPING_FAKEFOB_MQTT_USER` (`safeping-fob`) | publish `safeping/alert/<id>`, subscribe `safeping/ack/<id>` | yes |
| `server/fake_fob.py --type REF` over MQTT | `safeping-fob` | publish `safeping/ref/<id>` | **refused** (the Fob user may not publish there). Use `--direct` for REF |

Notes:
- EMQX may still answer a refused publish with a PUBACK and drop the message, depending on its deny setting. Then `fake_fob.py` says "no server ack in 3 s" instead of an error.
- The Fob's help rule is now `safeping/help/#`, wider than the `safeping/help/${clientid}` in the old notes, so any Fob login can hear every Fob's help messages. Help messages are signed per Fob and a Fob ignores any not meant for it, so this is safe, only less tight.

Old topics: nothing in the repo sends on `safeping/alerts` or `safeping/reference` any more. The Relay does not use MQTT, the Fob and the Reference board use their per-device topics, and `fake_fob.py` was the last sender. Dropping the two server subscriptions (and their rules) would change nothing today.

## 7. Free pins for the external NeoPixel

The Fob uses GPIO 1 (button), 3 (motor), 6 (LoRa RST), 8, 9, 10 (SPI), 11, 12 (GPS), 23, 24 (I2C), 26 (LoRa CS) and 27 (board LED).

| GPIO | Use it? | Why |
|---|---|---|
| **4** | **Yes, first choice** | Free, confirmed on a header hole by the pin walk (`docs/bench-log.md`), not a strapping pin |
| **5** | **Yes, second choice** | Same as 4 |
| 0 | Possible | Free and confirmed by the pin walk. On the ESP32-C5 it can also be a 32 kHz crystal pin. The board seems to have none (GPIO 1, its partner, works as the button), but I could not confirm it |
| 2 | No | Strapping pin (MTMS), read at reset. The old wiring plan used it |
| 7, 25, 28 | No | Strapping pins (25 is also the microSD, 28 the BOOT button) |
| 13, 14 | No | USB |

The ESP32-C5 strapping pins are GPIO 2, 3, 7, 25, 26, 27 and 28 (Espressif's ESP32-C5-DevKitC-1 user guide). The Fob already uses 3 and 26 and they work, because nothing pulls them at reset, but a NeoPixel's data input on one is a risk not worth taking.

Power from VBAT: the pixel reads a data "high" from 0.7 times its supply. At a full 4.2 V that is 2.94 V, and the board drives 3.3 V, so it works but with little margin. If it flickers at full charge and is fine later, that is why.

Tell me which GPIO you pick before you wire it, and I will check it again against anything new.

## 8. Guesses and things I could not do

1. **Relay (item 5): both statements were true.** The Relay's JSON check (decode, `json.loads`, must be an object with `sig`, `id` and `ctr`, else "ignored a packet that is not a SafePing alert") has been there since the merge commit. `firmware/relay/main.py` has one commit in git and no changes since. It prints `SAFEPING_MSG` only after that check. Nothing to copy.
2. **MicroPython 1.29 was checked on paper only**, from the 1.28 and 1.29 release notes and the 1.29 source (`modmachine.c`, `machine_pin.c`, `machine_rtc.c`, `mpconfigport.h`). Nothing was flashed. The release notes give commit titles only, so a behavior change hidden behind a title could be missed. The new I2C driver is the biggest unknown: the Reference board now scans first, but the Fob's battery gauge and sensor start the same way as before.
3. **Live SMS was tested against a fake Textbelt only.** The reply fields (`success`, `textId`, `quotaRemaining`, `error`) are from Textbelt's documented replies and your hand test. A text with characters outside plain ASCII would be sent as a longer (UCS-2) text, so names are reduced to plain characters ("Zoe" for "Zoë").
4. **The hourly cap counts texts tried**, not only texts that went through, so a run of failures also uses up the cap. That protects credits if something loops.
5. **Live texts are ignored on a test database** (any database in the temp folder). This protects every test, old and new, from a `TEXTBELT_KEY` left in the terminal. The real database is never in the temp folder, so it changes nothing for you.
6. **Number hashes.** `sms_numbers` and `sms_sent` store a hash, not the number. A 10-digit number can be found from its hash by trying every number, so treat the database as private (it already holds the device keys).
7. **Pushover now goes before the text** (it was after). A MEDICAL in Pushover repeats until answered, so it should never wait on a slow text.
8. **The settings file is read when each program starts.** Change the file, restart the program. Comments must be on their own line, because a password can hold `#`.
9. **The Reference board's BOOT report is QoS 0 and not retried.** If its one publish is lost, the readings still show it is alive. Its counter comes from the same block counter, so the readings after it still go up.
10. **The free-pin list** relies on the pin walk for which GPIOs reach header holes. Pins beyond IO0 to IO5 are not mapped yet.
11. **The dashboard** builds in both modes, but I did not look at the new Health row or the Reference board's Last start in a browser.
