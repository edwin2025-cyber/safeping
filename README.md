# SafePing Safety Fob

SafePing is a safety fob system built by Group 24, "The Inventors", for the ASCTE senior capstone. A student presses the Fob to send an alert, and the server shows it on a dashboard and texts the duty phone.

## Getting started

To run the server on your laptop, follow [Run it on your laptop](#run-it-on-your-laptop) below. Read [message-format.md](message-format.md) first: every device and the server share that one format.

## SafePing code

```
safeping/
  message-format.md        The one format every device and the server share. Read this first.
  firmware/
    fob/                   Fob firmware (MicroPython)
    relay/                 Relay: LoRa to WiFi/MQTT
    reference/             Reference: ground-floor pressure baseline
  docs/                    Test results, wiring diagram, meeting notes
  server/
    app.py                 Flask app: dashboard and API (also starts the MQTT listener)
    mqtt_listener.py       Subscribes to the broker
    processor.py           What happens to a message after it arrives
    validate.py            Signature, counter and device checks
    location.py            GPS, or floor from pressure
    notify.py              Text to the duty phone (Twilio)
    db.py                  SQLite tables
    config.py              Settings (environment variables)
    add_device.py          Register a Fob or the Reference and get its secret key
    fake_fob.py            Pretend Fob, for testing without hardware
    test_attacks.py        DT-04 test: forged, replayed and unknown-ID messages
    mosquitto.conf         Broker settings
    static/                The dashboard (index.html, dashboard.js, style.css)
```

Still to write: the Fob, Relay and Reference firmware (MicroPython).

## Run it on your laptop

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

6. Run the security test: `python test_attacks.py`

## Settings

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

## What has been tested

- The security test passes (16 of 16 checks) and the dashboard works in a browser on desktop and phone sizes.
- A full run worked end to end with a test MQTT broker (amqtt) and paho-mqtt 2.x: messages published over MQTT reached the database, the dry-run text and the API.
- Not yet tested: a real Mosquitto broker, real Twilio texts, the Leaflet map with internet access, and any firmware.

## Choices made that you can change

- **Rejected messages** go to their own `rejected` table, not just a log file. This is the open question in the spec.
- **The Reference signs its readings** the same way the Fobs do, so nobody can fake the floor calculation.
- **Names stay on the server.** The dashboard and the text show the student name, but no message from a device ever carries one.
- **Status checks** are saved but do not text anyone. The dashboard hides them unless you tick "Show status checks".
- **Alert history is kept forever.** Nothing deletes old alerts yet. Decide a retention rule and write it in the spec.
- **Texts are sent one at a time** inside the message handler, which is fine for a prototype. Smart Escalation (grouping alerts from several Fobs) is not built yet.
- **The dashboard login** is one shared password, off unless `DASHBOARD_PASSWORD` is set. It uses HTTP Basic, which is not encrypted on school WiFi without HTTPS. Fine for a demo, not for real use.
