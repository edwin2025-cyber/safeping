# SafePing Message Format (version 1)

Every device (Fob, Relay, Reference) and the server follow this one format. If you change it, change it here first, then in the code.

## Transport

| What | Topic | Sent by | QoS |
|---|---|---|---|
| Alerts from a Fob over WiFi | `safeping/alert/<id>` (for example `safeping/alert/FOB-001`) | Fob | 1 |
| Signed acks for WiFi alerts | `safeping/ack/<id>` | Server | 1 |
| Alerts (old shared topic, still read) | `safeping/alerts` | `fake_fob.py`, or a future Relay forwarder | 1 |
| Reference readings | `safeping/reference` | Reference | 1 |

The broker is EMQX Cloud Serverless. It takes **TLS only, on port 8883**, with a user name and password: `safeping-fob` for the Fobs and `safeping-server` for the server. Both sides check the broker's certificate against the CA file. Certificate checks are never turned off. The Fob checks the certificate date, so it needs a set clock (NTP). With the clock before 2026, it skips WiFi and uses LoRa (`clock_not_set`).

The Relay passes a LoRa packet on exactly as received. It does not edit or re-sign anything. The message is the same on every path. The server only records which path it came in on.

Two ways the Relay can pass alerts on:

- **MQTT** (planned): the Relay republishes to `safeping/alerts`.
- **USB serial bridge** (works now): the Relay is plugged into the server computer and prints each new alert as `SAFEPING_MSG <json>`. `server/serial_bridge.py` reads those lines and hands them to the same `processor.process()` the MQTT listener uses.

Size limits: an MQTT payload must be under 512 bytes. A LoRa packet holds at most **255 bytes**, and that is the real limit. The largest realistic alert (GPS, pressure, temperature, battery) is about 241 bytes, so keep device IDs short and do not add fields without checking.

## Fields

All numbers are **integers**. This is on purpose. The ESP32 uses single-precision floats, which cannot hold a GPS coordinate to 6 decimals, and floats print differently on different devices, which would break the signature.

| Field | Meaning | Required | Unit / values |
|---|---|---|---|
| `v` | Format version | yes | `1` |
| `id` | Device ID | yes | text, up to 32 characters, such as `FOB-001` |
| `type` | Message type | yes | `STATUS`, `SUSPICIOUS`, `MEDICAL`, `SILENT` (Fob) or `REF` (Reference) |
| `ctr` | Counter, goes up by at least 1 every message | yes | whole number, 0 or more |
| `ts` | Device clock | no | Unix seconds. Set by NTP once WiFi works, so the server also stamps its own time |
| `lat` | Latitude | no | microdegrees (34.730123 is `34730123`) |
| `lon` | Longitude | no | microdegrees (-86.586104 is `-86586104`) |
| `acc` | GPS accuracy | no | meters (the Fob estimates HDOP x 5) |
| `p` | Pressure | Reference: yes. Fob: no | pascals (101325) |
| `t` | Temperature | no | hundredths of a degree C (2150 is 21.50 C) |
| `bat` | Battery | no | percent, 0 to 100 |
| `sig` | Signature | yes | 64 lowercase hex characters |

Leave a field out when it has no value. Never send a name. Names live only on the server.

Example (a Silent alert with a GPS fix):

```json
{"v":1,"id":"FOB-001","type":"SILENT","ctr":42,"ts":1760650000,
 "lat":34730123,"lon":-86586104,"acc":8,"p":101240,"bat":87,
 "sig":"<64 hex characters>"}
```

## Signing

1. Build the **signing string** from these fields in this exact order, joined by `|`. A missing field is an empty string.

   `v | id | type | ctr | ts | lat | lon | acc | p | t | bat`

   For the example above: `1|FOB-001|SILENT|42|1760650000|34730123|-86586104|8|101240||87`

2. `sig = HMAC-SHA256(secret_key, signing string)`, written as lowercase hex.

Each device has its own `secret_key`, made by `server/add_device.py`. The server keeps a copy so it can check the signature.

## LoRa acks (Fob and Relay)

Over LoRa the Fob waits for the Relay to confirm it saved the alert.

1. The Relay stores each NEW alert in `queue.txt` on its flash, then answers with one short packet:

   `ACK <id> <ctr> <mac>`

   `mac` = the first 16 hex characters of `HMAC-SHA256(ack_key, "ACK|<id>|<ctr>|<the alert's sig>")`

   `ack_key` = `HMAC-SHA256(device secret_key, "safeping-ack-v1")`

2. The Relay holds only ack keys (in its own `config.py`, never in git), never the device secret. A stolen Relay could fake acks but never alerts.
3. The Fob listens up to 1 s for the exact ack. No valid ack: it sends the SAME message again (same `ctr`, same `sig`), up to 3 times. Still nothing: NOT CONFIRMED (orange light, long buzz).
4. A forged ack is rejected (`bad signature`). An old ack replayed for a new alert is rejected (`not for this alert`).
5. A resent alert is acked again by the Relay but stored and passed on only once.

The ack proves the Relay saved the alert. It does not yet prove the server saved it. The server can make the same ack (it knows every secret), so moving the ack to the server later keeps this format.

## WiFi acks (Fob and server, over MQTT)

Over WiFi the Fob waits for the **server** to confirm it saved the alert. The broker's own PUBACK only means the broker has it, so it does not count.

1. The Fob connects (TLS), **subscribes to `safeping/ack/<id>` first**, then publishes the alert to `safeping/alert/<id>` at QoS 1.
2. The server checks the alert as usual. **Only after the alert is saved** (before any text goes out), it publishes the ack to `safeping/ack/<id>` at QoS 1.
3. The ack text is exactly the LoRa ack: `ACK <id> <ctr> <mac>`, with the same `ack_key` and `mac` as above (`ackcheck.py`, shared by the Fob, the Relay and the server).
4. The Fob waits up to `MQTT_ACK_WAIT_MS` (2 s) for the exact ack and ignores anything else. Valid ack: confirmed, two pulses. No valid ack in time: it sends the **same message** (same `ctr`, same `sig`) over LoRa.
5. The server never acks a rejected message, except a duplicate (below).

The whole WiFi attempt (join, DNS, TLS, connect, publish, ack) has a hard limit of `WIFI_BUDGET_MS` (5 s). After that the Fob uses LoRa.

## Duplicates

Because the Fob resends the same message over LoRa when the WiFi ack is lost, the server can get one alert twice.

- A message that is **identical to an already accepted alert** (same `id`, `ctr` and `sig`) and arrives **within 10 minutes** of it is a `duplicate`:
  - it is not stored again and no second text is sent
  - it is written to the `rejected` table with reason `duplicate` (System health shows it as "Duplicates caught")
  - if it came over MQTT, the server acks it again, so the Fob stops resending
- Anything else with an old or reused counter is still `replay`: a different signature, a lower counter, an identical copy after 10 minutes, or a Reference reading.
- The duplicate check runs only after the signature is good, so it cannot be forged.

## What the server checks, in this order

1. Payload is under 512 bytes and is valid JSON. Otherwise `bad_json`.
2. Fields are present, whole numbers, and in range. Otherwise `bad_format`.
3. The ID is registered. Otherwise `unknown_device`.
4. The device is allowed to send this type (Fobs send alerts, the Reference sends `REF`). Otherwise `wrong_role`.
5. The signature matches. Otherwise `bad_signature`.
6. The counter is higher than the last accepted one for that device. Otherwise `replay`, or `duplicate` if it is an identical copy of an alert accepted in the last 10 minutes (see Duplicates).

The counter is only used up after the signature is good, so nobody can lock a device out with fake messages.

Every rejection is written to the `rejected` table with the reason. This is the log that DT-04 checks.

## The Fob's counter

The Fob saves its counter to flash BEFORE every send, so a crash or power loss can never reuse a number. A cancelled alert does not use a counter.

## Message types

| Type | Meaning | Text to duty phone | Shown on dashboard |
|---|---|---|---|
| `STATUS` | 1 press, status check | no | hidden by default, logged |
| `SUSPICIOUS` | 2 presses | yes | yes |
| `MEDICAL` | 3 or more presses | yes | yes |
| `SILENT` | hold (2 s on the bench, `HOLD_MS`; the PDR said 5 s) | yes | yes |
| `REF` | Reference pressure reading | no | status strip only |

## How location is decided

1. If the message has `lat` and `lon`, use them (with `acc`).
2. Otherwise, if it has `p` and the latest Reference reading is less than 120 seconds old, the floor is
   `1 + round((reference p - fob p) / PA_PER_FLOOR)`. The Reference sits on the ground floor, which the server calls floor 1.
   `PA_PER_FLOOR` defaults to 42 Pa. The floor walk on 2026-11-07 measured about 55 Pa per floor, with uneven floors (ground to 1st 68 Pa, then 54, then 42), so start the server with `PA_PER_FLOOR=55`. A per-floor table would be more accurate (planned).
3. Otherwise the alert is stored with no location.
