# SafePing Safety Fob

ASCTE senior capstone, Group 24 "The Inventors". A wearable fob a student presses to quietly alert staff when they feel unsafe and cannot safely use a phone.

One button, four alerts:

| Press | Alert | Light | Buzz |
|---|---|---|---|
| 1 press | STATUS (logged only) | dim white, then a green blink when confirmed | short |
| 2 presses | SUSPICIOUS | yellow, 2 s cancel window, then green when confirmed | one, then two medium when confirmed |
| 3 or more | MEDICAL | red, 2 s cancel window, then green when confirmed | pulsing, then two medium when confirmed |
| hold 2 s | SILENT | none, ever | short, then two medium when confirmed |

A tap in the 2 s window cancels (green blink). Not confirmed = orange light and one long buzz. All LED patterns: `docs/led-patterns.md`.

## How an alert travels

```
Fob --WiFi--> MQTT broker --> server --> database --> dashboard (+ text to duty phone)
Fob --LoRa--> Relay --(USB serial bridge, or MQTT later)--> server
Reference (pressure on the ground floor) --> server, to work out the floor indoors
```

Every alert is signed (HMAC-SHA256) and carries a counter, so the server rejects fakes and replays. Over LoRa the Relay sends back a signed ack. Details: `docs/message-format.md`.

## Folders

| Folder | What is in it |
|---|---|
| `firmware/fob/` | Fob program (`main.py`) and `config.example.py` |
| `firmware/relay/` | Relay program (`main.py`) and `config.example.py` |
| `firmware/reference/` | Reference board (ground floor pressure), not built yet |
| `firmware/lib/` | Drivers copied onto the boards: `sx127x.py` (LoRa), `gps.py`, `bme280.py`, `max17048.py` (battery), `ackcheck.py` |
| `firmware/bringup/` | First bring-up scripts from October |
| `firmware/archive/` | Old code kept for reference, not used |
| `server/` | Flask server, MQTT listener, validation, database, `serial_bridge.py`, dashboard in `server/static/` |
| `tests/` | Bench tools: `field_log.py` (logs Fob and Relay together), `motor_test.py`, `sensor_check.py`, range and radio tests, `lessons/` |
| `logs/` | Every bench run (raw, CSV, summary) and the index `logs/README.md` |
| `docs/` | Message format, wiring, bench log, range tests |

## What goes on each board (Thonny, Save as, MicroPython device)

| Board | Files |
|---|---|
| Fob | `firmware/fob/main.py` as `main.py`, plus `sx127x.py`, `gps.py`, `bme280.py`, `max17048.py`, `ackcheck.py` from `firmware/lib/`, plus its own `config.py` |
| Relay | `firmware/relay/main.py` as `main.py`, plus `sx127x.py` and `ackcheck.py`, plus its own `config.py` (ack keys) |

## Running the server on a laptop

```
cd server
python -m pip install -r requirements.txt
python -m pip install amqtt pyserial
```

Then in separate terminals:

1. Broker: `python -m amqtt.scripts.broker_script` (Mosquitto works too where it can be installed)
2. Server and dashboard: set `PA_PER_FLOOR` to 55, then `python app.py`, then open http://127.0.0.1:5000
   (PowerShell: `$env:PA_PER_FLOOR = "55"`)
3. Relay over USB: `python serial_bridge.py --port COM14 --echo`

Register a device once: `python add_device.py FOB-001 "Student Name"`. It prints the secret key. Put it in that Fob's `config.py` and nowhere else.

## Secrets (never in git)

- Every `config.py` under `firmware/` (the Fob's secret key, the Relay's ack keys, WiFi passwords).
- `server/safeping.db` (devices, keys, alerts).
- Backups live outside the repo in `Documents/safeping-private`.

`server/config.py` is the one tracked config: it only reads environment variables and holds no secrets.

## Dashboard

The staff dashboard is a React app in `dashboard/`. Build it once with `npm.cmd install` and `npm.cmd run build` in `dashboard/`, then `python app.py` in `server/` serves it at http://127.0.0.1:5000. Map tiles use CARTO when `CARTO_KEY` is set. Named campus places go in `server/places.json`. How to run it, the settings, places and the map math: [docs/dashboard.md](docs/dashboard.md). Screenshots: [docs/screenshots/](docs/screenshots/).

The Overview page shows alert totals, response times, when alerts happen and a CSV export for any date range.

## For the dashboard and login work

The dashboard is `server/static/` (served by `server/app.py`). Login and two-factor must be checked inside the Flask server (in front of `/api/alerts` and `/api/ack`), not only on a separate page, or anyone could open the server's address and skip it.

## History

This repo merged the bench repo `safeping-bench` on 2026-11-08. The bench repo is archived on GitHub with its full history.

## Notes kept from the old README

### Run it on your laptop

1. Install Python 3 and the packages: `pip install -r requirements.txt`
2. Install and start Mosquitto (a broker). Skip this if you only want to try `--direct` mode.
3. Register devices. Each prints a secret key:

   ```
   python add_device.py FOB-001 "Student Name"
   python add_device.py REF-01 --role REF
   ```

4. Start the server and open http://localhost:5000

   ```
   python app.py
   ```

5. In another window, send test messages (use the keys from step 3):

   ```
   python fake_fob.py --id REF-01 --key <ref key> --type REF --pressure 101325
   python fake_fob.py --id FOB-001 --key <fob key> --type SILENT --lat 34.7304 --lon -86.5861 --acc 8
   python fake_fob.py --id FOB-001 --key <fob key> --type MEDICAL --pressure 101241
   ```

   Add `--direct` to skip the broker and hand the message straight to the server code.

   Fob console output from Wokwi can be fed to the server with `python replay_serial.py serial.txt`.

6. Run the security test: `python test_attacks.py`

### Settings

Set these as environment variables. All are optional.

| Name | What it does | Default |
|---|---|---|
| `MQTT_HOST`, `MQTT_PORT` | Where the broker is | `localhost`, `1883` |
| `MQTT_USER`, `MQTT_PASS` | Broker login | none |
| `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM` | Twilio account | none (texts are printed, not sent) |
| `DUTY_PHONES` | Numbers to text, comma separated | none |
| `PA_PER_FLOOR` | Pascals of pressure change per floor | 42 (calibrate it) |
| `DASHBOARD_PASSWORD` | Turns on a shared dashboard login | no login |
| `SAFEPING_DB` | Database file | `server/safeping.db` |

### What has been tested

- The security test passes (16 of 16 checks) and the dashboard works in a browser on desktop and phone sizes.
- A full run worked end to end with a test MQTT broker (amqtt) and paho-mqtt 2.x: messages published over MQTT reached the database, the dry-run text and the API.
- The Fob firmware passes its simulation test (firmware/fob/sim_test.py, 48 checks against the real server code). It has not run on real hardware or in Wokwi yet.
- The part drivers (battery gauge, pressure sensor, GPS, LoRa radio) pass their desktop tests against known-good values and a software model of the radio (firmware/common/test_drivers.py). The bring-up scripts pass a fake-parts test (firmware/bringup/test_scripts.py). None of this has run on real parts yet.
- Not yet tested: a real Mosquitto broker, real Twilio texts, the Leaflet map with internet access, and any firmware on real hardware.

### Choices made that you can change

- **Rejected messages** go to their own `rejected` table, not just a log file. This is the open question in the spec.
- **The Reference signs its readings** the same way the Fobs do, so nobody can fake the floor calculation.
- **Names stay on the server.** The dashboard and the text show the student name, but no message from a device ever carries one.
- **Status checks** are saved but do not text anyone. The dashboard hides them unless you tick "Show status checks".
- **Alert history is kept forever.** Nothing deletes old alerts yet. Decide a retention rule and write it in the spec.
- **Texts are sent one at a time** inside the message handler, which is fine for a prototype. Smart Escalation (grouping alerts from several Fobs) is not built yet.
- **The dashboard login** is one shared password, off unless `DASHBOARD_PASSWORD` is set. It uses HTTP Basic, which is not encrypted on school WiFi without HTTPS. Fine for a demo, not for real use.
