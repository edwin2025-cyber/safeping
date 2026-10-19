# SafePing Message Format (version 1)

Every device (Fob, Relay, Reference) and the server follow this one format. If you change it, change it here first, then in the code.

## Transport

| What | Topic | Sent by | Over |
|---|---|---|---|
| Alerts | `safeping/alerts` | Fob (WiFi), or Relay on behalf of a Fob (LoRa) | MQTT |
| Reference readings | `safeping/reference` | Reference | MQTT |

The Relay republishes a LoRa packet to `safeping/alerts` exactly as received. It does not edit or re-sign anything. The server cannot tell which path a message took.

Payload is one JSON object, UTF-8, under 512 bytes.

## Fields

All numbers are **integers**. This is on purpose. The ESP32 uses single-precision floats, which cannot hold a GPS coordinate to 6 decimals, and floats print differently on different devices, which would break the signature.

| Field | Meaning | Required | Unit / values |
|---|---|---|---|
| `v` | Format version | yes | `1` |
| `id` | Device ID | yes | text, up to 32 characters, such as `FOB-001` |
| `type` | Message type | yes | `STATUS`, `SUSPICIOUS`, `MEDICAL`, `SILENT` (Fob) or `REF` (Reference) |
| `ctr` | Counter, goes up by at least 1 every message | yes | whole number, 0 or more |
| `ts` | Device clock | no | Unix seconds. May be wrong until NTP is added, so the server also stamps its own time |
| `lat` | Latitude | no | microdegrees (34.730123 is `34730123`) |
| `lon` | Longitude | no | microdegrees (-86.586104 is `-86586104`) |
| `acc` | GPS accuracy | no | meters |
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

Each device has its own `secret_key`. The server keeps a copy so it can check the signature.

## What the server checks, in this order

1. Payload is under 512 bytes and is valid JSON. Otherwise `bad_json`.
2. Fields are present, whole numbers, and in range. Otherwise `bad_format`.
3. The ID is registered. Otherwise `unknown_device`.
4. The device is allowed to send this type (Fobs send alerts, the Reference sends `REF`). Otherwise `wrong_role`.
5. The signature matches. Otherwise `bad_signature`.
6. The counter is higher than the last accepted one for that device. Otherwise `replay`.

The counter is only used up after the signature is good, so nobody can lock a device out with fake messages.

Every rejection is written to the `rejected` table with the reason. This is the log that DT-04 checks.

## The Fob's counter

The Fob must save its counter to flash after every send. If it restarts at 0, the server will reject everything until the counter passes the old value.

## Message types

| Type | Meaning | Text to duty phone | Shown on dashboard |
|---|---|---|---|
| `STATUS` | 1 press, status check | no | hidden by default, logged |
| `SUSPICIOUS` | 2 presses | yes | yes |
| `MEDICAL` | 3 or more presses | yes | yes |
| `SILENT` | hold 5 seconds | yes | yes |
| `REF` | Reference pressure reading | no | status strip only |

## How location is decided

1. If the message has `lat` and `lon`, use them (with `acc`).
2. Otherwise, if it has `p` and the latest Reference reading is less than 120 seconds old, the floor is
   `1 + round((reference p - fob p) / PA_PER_FLOOR)`. `PA_PER_FLOOR` starts at 42 Pa and must be calibrated by walking the building (DT-08).
3. Otherwise the alert is stored with no location.
