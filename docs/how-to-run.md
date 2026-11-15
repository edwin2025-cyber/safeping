# How to run SafePing

Quick steps for every part of the project. Run everything from VS Code's terminal: press **Ctrl+`** in the `safeping` folder.

Notes for this laptop:
- Use `npm.cmd`, not `npm`. PowerShell blocks `npm.ps1`.
- To use more than one program at a time, open another terminal with the **+** button.
- Ctrl+C stops whatever is running in a terminal.
- Keys and passwords live in `Documents\safeping-private`. Never paste them into chat, a screenshot or a commit.

---

## 0. Settings file (`safeping.env`), make it once

Every setting the server and the laptop tools need lives in one file:

`Documents\safeping-private\safeping.env`

`app.py`, `serial_bridge.py`, `mqtt_listener.py`, `fake_fob.py`, `tests\field_log.py`, `tests\broker_check.py`, `tests\ref_calibrate.py` and `tests\survey_analyze.py` read it when they start. They print only the names they loaded, never a value, for example:

```
Settings: 14 names from C:\Users\...\Documents\safeping-private\safeping.env (CARTO_KEY, PA_PER_FLOOR, ...)
```

How to make it:
1. Open Notepad, paste the template below, and fill in the real values from `safeping-private` (the old `carto_key.txt` and `pushover.txt` values go in here too).
2. Save it as `safeping.env` in `Documents\safeping-private`. In Notepad's Save dialog, set "Save as type" to "All files", or Notepad adds `.txt`.

Rules:
- One `NAME=value` per line. Spaces around `=` are fine. Quotes around a value are fine.
- Comments on their own line, starting with `#`. Not at the end of a line (a password can hold `#`).
- Leave a line out, or the value empty, to use the default.
- Never put the file in the repo folder. The server refuses to read it there, and `.gitignore` ignores every `*.env` file.
- Another place: set `$env:SAFEPING_ENV_FILE` to the full path.
- `$env:NAME = "..."` in the terminal still works and **wins over the file**, for one session. Example: `$env:NO_MQTT = "1"` to start once without MQTT.
- After you change the file, restart the program.

### Template (placeholders only)

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

The old names `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS` and `MQTT_CA` still work when the `SAFEPING_MQTT_*` ones are not set (the local Mosquitto setup).

---

## 1. Dashboard

### Fake data, no server (design work)
```
cd dashboard
npm.cmd run dev:mock
```
Open http://localhost:5173. The page updates as you edit the code.

For CARTO map tiles in mock mode, `dashboard\.env.mock.local` must hold `VITE_CARTO_KEY=...`. Git ignores that file.

### Real data
```
cd server
python app.py
```
Settings come from `safeping.env` (section 0). To start once without the broker: `$env:NO_MQTT = "1"` before `python app.py`.

Open http://127.0.0.1:5000.

This serves the last **built** dashboard. If you changed dashboard code, rebuild first:
```
cd dashboard
npm.cmd run build
```

### Real data with live editing
1. Terminal 1: the server, as above.
2. Terminal 2:
   ```
   cd dashboard
   npm.cmd run dev
   ```
3. Open http://localhost:5173.

### Checks after dashboard changes
```
cd dashboard
npm.cmd run contrast
npm.cmd run build
```

---

## 2. Real alerts from the Relay (LoRa over USB)

The server must already be running (section 1, real data).

New terminal:
```
cd server
python serial_bridge.py
```
Add `--echo` to see everything the Relay prints. It reads `safeping.env` too, so LoRa alerts get Pushover and texts like WiFi ones.

Only one program can use COM14 at a time. Close Thonny on the Relay first. Do not run the bridge and the field logger together.

---

## 3. Field tests (logger)

Plug the Relay into COM14. For tests that log the Fob too, plug it into COM15. Start the logger **before** opening Thonny.

### Relay only (Fob on its battery, out in the field)
```
python tests\field_log.py --label NAME --relay COM14 --no-fob
```

### Relay and Fob (both on USB, at the desk)
```
python tests\field_log.py --label NAME --relay COM14
```

### Fob only
```
python tests\field_log.py --label NAME
```

The Relay port is opened only when `--relay` is given.

Add `--forward` to send each Relay alert to the server too, the same way `serial_bridge.py` does. Use it when the website must show the alerts during a test. The bridge cannot run at the same time, because the logger holds the Relay's port.

- Replace `NAME` with something short, like `dt10_run2` or `failover_pre_t1`.
- Ctrl+C stops it and prints the summary.
- Each run gets its own folder in `logs\<date>\`.
- `python tests\field_log.py --help` lists every option.

---

## 4. Server tests and tools

All from the `server` folder:
```
cd server
```

| What | Command |
|---|---|
| Security test (must say 19 of 19) | `python test_attacks.py` |
| Duplicate and replay rule, counter window (must say 58 of 58) | `python test_duplicates.py` |
| Serial bridge reads Relay lines with left-over bytes (must say 17 of 17) | `python test_serial_bridge.py` |
| Pushover notifications, against a fake Pushover (must say 81 of 81) | `python test_pushover.py` |
| Text messages, against a fake Textbelt (must say 50 of 50) | `python test_textbelt.py` |
| Settings file loader, with fake files (must say 42 of 42) | `python test_envfile.py` |
| Reference board on the server (must say 27 of 27) | `python test_reference.py` |
| Register a device | `python add_device.py FOB-001 "Student name" --key <key from safeping-private>` |
| Send a fake alert | `python fake_fob.py --id FOB-001 --key <key> --type MEDICAL` over the broker (uses `SAFEPING_FAKEFOB_MQTT_USER` and `_PASS`, waits for the server's ack), or add `--direct` to skip the broker |

### Fob laptop tests (no board needed)
From the `safeping` folder:

| What | Command | Must say |
|---|---|---|
| WiFi budget and fallback | `python tests\test_sendpath.py` | 37 of 37 |
| WiFi error reasons | `python tests\test_wifi_errors.py` | 58 of 58 |
| Retry queue and button presses | `python tests\test_retry_queue.py` | 71 of 71 |
| Help is coming (WiFi) | `python tests\test_help.py` | 51 of 51 |
| Boot self-check, boot report, BOOT sent after a press | `python tests\test_selfcheck.py` | 57 of 57 |
| LED colors (one meaning per color) | `python tests\test_led.py` | 30 of 30 |
| No imports inside functions, no flash during HELP_LISTEN | `python tests\test_imports.py` | 32 of 32 |
| Counter file | `python tests\test_counter.py` | 22 of 22 |
| Press kept through a crash | `python tests\test_press_record.py` | 55 of 55 |
| Reference board firmware | `python tests\test_ref.py` | 78 of 78 |
| Survey mode | `python tests\test_survey.py` | 83 of 83 |
| Calibration and survey analysis on fake data | `python tests\test_survey_analyze.py` | 54 of 54 |
| BOOT report retry, external LED, 1.29 TLS error text | `python tests\test_cleanup.py` | 38 of 38 |

### Start fresh before formal tests (archive the database)
1. Stop the server.
2. Move the old database out of the way:
   ```
   Move-Item server\safeping.db* ..\safeping-private\archive\
   ```
3. Start the server. It makes a new empty database.
4. Register the devices again with `add_device.py` and their saved keys.

---

## 5. The boards (Thonny)

- **Fob:** COM15. **Relay:** COM14.
- **To stop a running program:** click in the Shell and press **Ctrl+C**. Do not use the Stop button, which causes write timeouts.
- **To run a script from the laptop without saving it to the board:** open it in Thonny (File > Open > This computer) and press **F5**.
- **To edit the board's settings:** View > Files, then double-click `config.py` under "MicroPython device". Save with Ctrl+S.
- **After changing `config.py`:** press the board's **RST** button. Unplugging USB does not reset it while the LiPo is attached.
- **WiFi check (Fob):** open `tests\wifi_check.py` and press F5.
- **LoRa only on the Fob:** set `WIFI_SSID = "none"` in its `config.py`.

Battery rules:
- Only charge the LiPo while you are awake.
- Unplug the LiPo from the board whenever you leave the board alone.

---

## 6. Phone pages (range-logger on GitHub Pages)

- **Floor walk:** `floor.html`
- **DT-10 GPS test:** `dt10.html`
- **Floor survey:** `survey.html` (works offline after one load)

Before each test, tap **Clear all** twice. After each test, tap **Export CSV** and put the file in that test's `logs\` run folder.

---

## 7. Committing

```
git status
```
**Make sure none of these appear:** `.env` or `safeping.env` files, `.db` files, `carto_key.txt`, any `config.py` from `firmware\` or `tests\`.

Then:
```
git add -A
git commit -m "Short description of what changed"
git push
```
No Co-Authored-By lines.

---

## 8. Cloud broker (EMQX Cloud Serverless)

The Fob sends over WiFi to the cloud broker first, then LoRa. The server reads the broker and sends each Fob a signed ack once its alert is saved. TLS only, port 8883.

Logins:
- `safeping-fob`: used by the Fobs and by `fake_fob.py` (its own settings `SAFEPING_FAKEFOB_MQTT_USER` and `_PASS`)
- `safeping-server`: used by the server and `tests\broker_check.py`
- `safeping-ref`: used by the Reference board

The broker is whitelist only. What each login may do:

| Login | Publish | Subscribe |
|---|---|---|
| `safeping-fob` | `safeping/alert/#`, `safeping/survey/#` | `safeping/ack/#`, `safeping/help/#` |
| `safeping-server` | `safeping/ack/#`, `safeping/help/#`, `safeping/test/#` | `safeping/alert/#`, `safeping/alerts`, `safeping/survey/#`, `safeping/ref/#`, `safeping/reference`, `safeping/test/#` |
| `safeping-ref` | `safeping/ref/#` | nothing |

The server's settings are the `SAFEPING_MQTT_*` lines in `safeping.env` (section 0). With `SAFEPING_MQTT_CA` set, the server uses TLS and checks the certificate. The port defaults to 8883 then.

Check the broker first:
```
python tests\broker_check.py
```

### Start the server with MQTT on
Do **not** set `NO_MQTT` (in the file or the terminal):
```
cd server
Remove-Item Env:NO_MQTT -ErrorAction SilentlyContinue
python app.py
```
You should see `[mqtt] connected to ...:8883 with TLS`. For each Fob alert:
- `[mqtt] ack sent to safeping/ack/FOB-001 ctr 212`
- `[mqtt] safeping/alert/FOB-001 -> {...}`

The ack line comes first, because the ack goes out as soon as the alert is saved.

To run only the listener (no dashboard): `python mqtt_listener.py`.

### The Fob's `config.py`
Add these lines. Use the real values from `safeping-private`:
```
WIFI_SSID = "the-wifi-name"
WIFI_PASSWORD = "the-wifi-password"
MQTT_HOST = "your-deployment-address"
MQTT_PORT = 8883
MQTT_USER = "safeping-fob"
MQTT_PASSWORD = "the-fob-broker-password"
MQTT_TLS = True
MQTT_CA_FILE = "/certs/broker-ca.pem"
WIFI_BUDGET_MS = 5000
WIFI_JOIN_MS = 3000
MQTT_ACK_WAIT_MS = 2000
WATCHDOG_ENABLED = False
STATUS_SUCCESS_PATTERN = "ok"
```
- `WIFI_TIMEOUT_MS`, `SEND_ATTEMPTS` and `MQTT_PASS` are old names. You can delete them. `MQTT_PASS` still works if `MQTT_PASSWORD` is missing.
- `WIFI_SSID = "none"` still means LoRa only.

### The CA file on the Fob
1. In Thonny: View > Files. Under "MicroPython device", right-click and make a new folder called `certs` (at the top level, so the path is `/certs`).
2. On "This computer", find the CA file in `safeping-private`. Right-click it > Upload to `/certs`.
3. On the board, rename it to `broker-ca.pem`.
4. Press RST. The boot lines must **not** say `TLS CA file missing`.

The Fob reads the CA as PEM. If the board refuses PEM, it turns it into DER by itself. If that also fails, convert it on the laptop and point the Fob at the DER file:
```
python -c "import ssl; open('broker-ca.der','wb').write(ssl.PEM_cert_to_DER_cert(open('broker-ca.pem').read()))"
```
Then upload `broker-ca.der` to `/certs` and set `MQTT_CA_FILE = "/certs/broker-ca.der"`.

### Reading the Fob's log
Every press ends with one line, for example:
```
SEND_RESULT ctr=212 kind=SUSPICIOUS path=wifi result=confirmed ms=840 reason=-
```
`reason` says why WiFi was not used: `wifi_off`, `wifi_join_failed`, `dns_failed`, `tls_failed`, `connect_timeout`, `connect_failed`, `no_server_ack`, `clock_not_set`, `ca_missing`, `ackcheck_missing`, `budget_exceeded`, or `-`. `field_log.py` puts `path`, `result`, `ms` and `reason` in the CSV.

Other lines the logger records (see `docs/message-format.md`):
- `SELF_CHECK key=ok counter=ok lora=ok gps=ok battery=ok pressure=ok wifi=ok fw=...` once per power on.
- `RETRY_QUEUED`, `RETRY_TRY`, `RETRY_DONE`, `RETRY_GAVE_UP`, `RETRY_STOPPED` for the retry queue. A retry's `SEND_RESULT` ends with `try=N`.
- `HELP_LISTEN`, `HELP_RECEIVED ctr=... ms_after_confirm=...`, `HELP_TIMEOUT`, `HELP ignored: ...` for "help is coming".
- `BOOT_STOPPED ctr=...` when a press stops the boot report, and `BOOT_RESEND ctr=...` when it is sent later.

### EMQX permissions for "help is coming"
In the EMQX console (Access Control > Authorization):
- `safeping-fob`: allow **subscribe** to `safeping/help/${clientid}`. The Fob's MQTT client id is its device id (`FOB-001`), so each Fob can only hear its own help messages. If you prefer fixed rules, add `safeping/help/FOB-001` (one rule per Fob).
- `safeping-server`: allow **publish** to `safeping/help/#`.
- All Fobs share the user name `safeping-fob`, so do not use `${username}` here.

Until then the Fob logs "help topic refused by the broker" and alerts still work as before.

---

## 9. Pushover notifications

The server sends a Pushover notification for every MEDICAL, SUSPICIOUS and SILENT alert, before the text message (section 10). Never for STATUS, BOOT, a duplicate or a replay.
- MEDICAL: emergency. It repeats every 60 s until someone acknowledges it in the Pushover app, for at most 30 minutes.
- SUSPICIOUS: high priority.
- SILENT: normal priority, no sound.

The two values are `SAFEPING_PUSHOVER_USER` and `SAFEPING_PUSHOVER_TOKEN` in `safeping.env` (section 0), copied from `pushover.txt`. Optional: `SAFEPING_PUBLIC_URL` (the address staff open the dashboard with) puts a link to the alert in each notification.

- The serial bridge reads the same file, so LoRa alerts are sent too.
- At start the server prints `[Pushover] on`, or `[Pushover] Pushover off (...)` if a value is missing. Alerts still work when it is off.
- A failed send prints `[Pushover failed] alert 12: ...`. It never stops the alert.
- Settings > Health > Pushover shows the last send and the last error. Red when the newest send failed.
- To turn it off: delete or comment out the two lines in `safeping.env` and restart.

---

## 10. Text messages (Textbelt)

The server texts the numbers in `SAFEPING_SMS_TO` for every new MEDICAL, SUSPICIOUS and SILENT alert, after Pushover. Never for STATUS, BOOT, REF, SURVEY, a duplicate or a replay. Settings in `safeping.env`:

| Name | What |
|---|---|
| `SAFEPING_SMS` | `off`, `dry` (print the text, send nothing; the default) or `live` |
| `TEXTBELT_KEY` | the Textbelt key |
| `SAFEPING_SMS_TO` | 10-digit numbers, comma separated |
| `SAFEPING_SMS_MAX_PER_HOUR` | at most this many texts in any hour, all alerts together (20) |

The text, at most 160 characters, sender "SafePing":

```
SafePing MEDICAL: Student Name (FOB-001). Near the bus loop. Pressed 2:14 PM. Reply STOP to opt out
```

- "arrived late at ..." is added when the alert came in late, "Press time unknown" when the Fob had no clock.
- "Reply STOP to opt out" is only on the first text each number ever gets.
- One text per alert per number. Over the hourly cap, the text is not sent and the server prints `[SMS] hourly cap of 20 texts reached`.
- At start: `[SMS] live through Textbelt. Numbers: ...01, ...02. At most 20 texts per hour`, or `[SMS] dry run ...`, or `[SMS] off`. Numbers are only ever shown as their last 2 digits. The key is never printed.
- Each text prints `[SMS] alert 12 sent to ...01 (text 1234, 39 credits left)`, or `[SMS failed] ...`. A failed text never stops the alert, the ack or Pushover.
- Settings > Health > Text messages: the mode, last send, last error and credits left. Orange under 25 credits, or when the newest text failed.
- To try it safely: keep `SAFEPING_SMS=dry` and watch the `[SMS dry run]` lines. Then set `live`.
- The tests never send a real text: live mode is ignored while the database is a test database in the temp folder.

---

## 11. MicroPython 1.29 (Reference board first, then the Fob)

What changed from 1.27 that matters here (checked against the 1.28 and 1.29 release notes and the 1.29 source):
- **Flash:** the ESP32-C5 build no longer turns on `free_ram` (`CONFIG_SPI_FLASH_ROM_IMPL`), the setting suspected in the 2026-11-11 and 2026-11-13 cache-error crashes (`docs/features-changes.md`). There is a new optional QIO 80 MHz flash setting. Nothing in our code depends on the flash mode.
- **I2C:** a new I2C driver (ESP-IDF 5.5.2). Same `machine.I2C(0, scl=..., sda=..., freq=...)`. The Reference board now scans the bus first and only tries the addresses that answer.
- **Reset cause:** the same numbers (1 power on, 2 crash or software reset, 3 watchdog, 4 deep sleep, 5 soft reset). Nothing to change.
- **Button interrupt:** `Pin.irq` still has no hard mode on the ESP32. The Fob already falls back to a soft interrupt (the boot line says `Button: soft interrupt`).
- **RTC memory:** `machine.RTC().memory()` still holds 2048 bytes on every ESP32 chip. The press record keeps working.
- **TLS errors:** since 1.28 they can carry the error's name as text (`MBEDTLS_ERR_SSL_TIMEOUT`). `sendpath.py` and `umqtt_safe.py` now read both forms, so the `reason` in `SEND_RESULT` stays right.
- Both boards print `MicroPython 1.29.0` (or `1.27.0`) at boot.

### Reference board (no data to lose)
1. Download 1.29.0 for **SparkFun Thing Plus ESP32-C5** from micropython.org (the board page, not the generic C5 file).
2. Flash it as in `docs/reference-survey-changes.md` section 5B (Thonny, "Erase all flash" ticked).
3. Copy every Reference board file and `/certs` again, then `config.py`. Press RST and check `MicroPython 1.29.0`, the `SENSOR` line and `REF_SENT` every 30 s.
4. Let it run 2 days. The dashboard top bar must stay green. Any crash shows as "Restarted after a crash" on the Devices page (its BOOT report).

### Fob (only after the Reference board behaved)
1. **Back up**, in Thonny (View > Files, MicroPython device, right-click > Download to `Documents\safeping-private\fob-backup-<date>\`):
   - `counter.txt` (and `counter.txt.tmp` if it is there)
   - `config.py`
   - the whole `/certs` folder
   - `queue.json` (and `queue.json.tmp`), if there
   - the `survey_q` folder, if there
   Open the backed-up `counter.txt` on the laptop and write the number down.
2. **Flash** 1.29.0 for SparkFun Thing Plus ESP32-C5, "Erase all flash" ticked.
3. **Restore**: make `/certs` and upload the CA file, upload `config.py`, `counter.txt`, `queue.json` and `survey_q` if you had them, then every Fob file from the copy list (`docs/env-sms-cleanup-changes.md` section 4). All at the top level `/`.
4. **Check the counter**: in the Thonny shell, `open("counter.txt").read()` must show the number you wrote down. If `counter.txt` was lost, the Fob jumps ahead from the clock at its first boot with WiFi. Do not register the Fob again.
5. **Flash stress test**: open `tests\flash_stress.py` in Thonny (This computer) and press F5. It writes only `stress.tmp` and `stress.json`. It must finish all 3000 cycles with no Guru Meditation. Save the Shell text with the results.
6. Press RST. Check `MicroPython 1.29.0`, the `SELF_CHECK` line (all ok) and a confirmed BOOT report, then press each alert type once.
7. If anything is wrong: flash 1.27.0 again and restore the same backup.
