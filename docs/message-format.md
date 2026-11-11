# SafePing Message Format (version 1)

Every device (Fob, Relay, Reference) and the server follow this one format. If you change it, change it here first, then in the code.

## Transport

| What | Topic | Sent by | QoS |
|---|---|---|---|
| Alerts from a Fob over WiFi | `safeping/alert/<id>` (for example `safeping/alert/FOB-001`) | Fob | 1 |
| Signed acks for WiFi alerts | `safeping/ack/<id>` | Server | 1 |
| "Help is coming" (staff pressed Acknowledge) | `safeping/help/<id>` | Server | 1 |
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
| `type` | Message type | yes | `STATUS`, `SUSPICIOUS`, `MEDICAL`, `SILENT`, `BOOT` (Fob) or `REF` (Reference) |
| `ctr` | Counter, goes up by at least 1 every message | yes | whole number, 0 or more |
| `ts` | Device clock at the press | no | Unix seconds. Set by NTP once WiFi works. Left out while the clock is not set. The server also stamps its own time |
| `lat` | Latitude | no | microdegrees (34.730123 is `34730123`) |
| `lon` | Longitude | no | microdegrees (-86.586104 is `-86586104`) |
| `acc` | GPS accuracy | no | meters (the Fob estimates HDOP x 5) |
| `p` | Pressure | Reference: yes. Fob: no | pascals (101325) |
| `t` | Temperature | no | hundredths of a degree C (2150 is 21.50 C) |
| `bat` | Battery | no | percent, 0 to 100 |
| `sig` | Signature | yes | 64 lowercase hex characters |
| `fail` | BOOT only: required self-checks that failed | BOOT: yes | bit mask, 0 = all passed (see Boot report) |
| `wifi` | BOOT only: WiFi joined at power on | no | `1` or `0`. Information only, never a failure |
| `fw` | BOOT only: firmware version | no | text, 1 to 16 of `A-Z a-z 0-9 . _ -`, such as `2026.11.11` |
| `rst` | BOOT only: why the Fob started, `machine.reset_cause()` | no | `1` power on (or RST button, or a battery dip), `2` after a crash, `3` watchdog, `4` deep sleep, `5` soft reset (Thonny), `0` unknown |

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

   A `BOOT` message adds more fields at the end, so every other message is signed exactly as before:

   `v | id | type | ctr | ts | lat | lon | acc | p | t | bat | fail | wifi | fw | rst`

   A `BOOT` from firmware older than `2026.11.11b` has no `rst` and is signed without it (`... | fail | wifi | fw`). The server accepts both.

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

1. The Fob connects (TLS), **subscribes to `safeping/ack/<id>` first** (and to `safeping/help/<id>` in the same packet, see "Help is coming"), then publishes the alert to `safeping/alert/<id>` at QoS 1.
2. The server checks the alert as usual. **Only after the alert is saved** (before any text goes out), it publishes the ack to `safeping/ack/<id>` at QoS 1.
3. The ack text is exactly the LoRa ack: `ACK <id> <ctr> <mac>`, with the same `ack_key` and `mac` as above (`ackcheck.py`, shared by the Fob, the Relay and the server).
4. The Fob waits up to `MQTT_ACK_WAIT_MS` (2 s) for the exact ack and ignores anything else. Valid ack: confirmed, two pulses. No valid ack in time: it sends the **same message** (same `ctr`, same `sig`) over LoRa.
5. The server never acks a rejected message, except a duplicate (below).

The whole WiFi attempt (join, DNS, TLS, connect, publish, ack) has a hard limit of `WIFI_BUDGET_MS` (5 s). After that the Fob uses LoRa.

## Counters, duplicates and replays

The Fob can send one signed message more than once: over LoRa after a lost WiFi ack, and again from its retry queue (below). The retry queue also means a real alert can arrive AFTER a newer one. So the server no longer asks "is this the highest counter?". It keeps a record of every counter it has accepted from each Fob (the `accepted_sigs` table: device, counter, signature, time), and applies these rules, in this order, after the signature is good:

1. **Counter already seen, same signature** (an exact copy of a saved message): `duplicate`, no matter how old.
   - not stored again, no second text
   - written to the `rejected` table as `duplicate` (System health: "Duplicates caught"). Not a security event
   - acked again (MQTT), so the Fob stops resending
2. **Counter already seen, different signature**: `replay`. A security event (red on System health).
3. **Counter never seen, and no more than `COUNTER_WINDOW` (32) below the highest counter seen for this Fob**: accepted, even if a higher counter got in first. The same with or without `ts`.
4. **Counter never seen, but more than `COUNTER_WINDOW` below the highest**: `replay`. Not stored, not acked. A security event.

A counter higher than any seen is always inside the window, so a Fob whose counter jumped ahead (a damaged counter file restarts from the clock) still works.

**Age never rejects an alert.** The server compares the alert's `ts` (the Fob's clock at the press) with its own clock:
- more than `LATE_AFTER_S` (60 s): accepted, tagged "Sent late" on Live, in the alert panel and in the exports
- more than `MAX_ALERT_AGE_S` (900 s): accepted, tagged "Sent late (over 15 min)", and Settings > Health shows a yellow warning ("Sent late (over 15 min)" with the count). It may be a long outage, or a recorded alert played back, so staff should check it
- no `ts`: no tag, because the press time is not known

The record of seen counters lives in the database, so the rules work after a server restart. Entries older than `SEEN_KEEP_DAYS` (7 days) are pruned, at most once an hour, but a counter inside the window is never pruned. So an exact copy inside the window is always a `duplicate`, and an older copy is below the window and a `replay`. It is never stored twice.

A Reference reading (`REF`) keeps the simple rule: its counter must go up, otherwise `replay`. It is never a duplicate.

Two copies of one message arriving at the same moment (WiFi and LoRa) cannot both be stored: claiming a counter is one database insert with a unique index on (device, counter).

What the window costs: someone who records a real alert that never reached the server (for example by jamming the Relay) can play it back later, as long as the Fob has sent fewer than 32 messages since. It is accepted, but its `ts` gives it away: "Sent late (over 15 min)" and the yellow Health warning. With no `ts` (Fob clock not set) nothing gives it away.

### When the Fob has no clock

The Fob sets `ts` from its own clock, which NTP sets once WiFi works. Until then (no WiFi since power on) the clock reads the year 2000, and the Fob leaves `ts` out. It does not send a wrong time. Over WiFi this cannot happen: TLS needs the date, so the Fob skips WiFi (`clock_not_set`) and uses LoRa.

With the counter window, such an alert is accepted even when a newer alert got in first. What is lost without `ts` is the age: no "Sent late" tag, and no warning for a played-back alert. Planned firmware change: set the Fob's clock from GPS time when NTP has not run (see `docs/features-changes.md`).

## What the server checks, in this order

1. Payload is under 512 bytes and is valid JSON. Otherwise `bad_json`.
2. Fields are present, whole numbers, and in range. Otherwise `bad_format`.
3. The ID is registered. Otherwise `unknown_device`.
4. The device is allowed to send this type (Fobs send alerts and `BOOT`, the Reference sends `REF`). Otherwise `wrong_role`.
5. The signature matches. Otherwise `bad_signature`.
6. The counter rule above: `duplicate` or `replay`, or accepted.

The counter is only used up after the signature is good, so nobody can lock a device out with fake messages. A message turned away as `replay` does not use up its counter.

Every rejection is written to the `rejected` table with the reason. This is the log that DT-04 checks.

## The Fob's counter

The Fob saves its counter to flash BEFORE every send, so a crash or power loss can never reuse a number. A cancelled alert does not use a counter. A `BOOT` report uses a counter like any message. A retry does NOT use a new counter: it is the same signed message.

## Retry queue (Fob)

An alert that ends NOT confirmed on both paths (WiFi, then LoRa) is kept and sent again.

- The alert is signed once, at the press. Every retry sends the exact same message (same `ctr`, `ts` and `sig`). Extra copies are `duplicate` at the server.
- A retry every `RETRY_EVERY_MS` (30 s) for `RETRY_FOR_MS` (10 minutes), then the Fob gives up. Each retry uses the normal WiFi-then-LoRa logic and budget. 10 minutes is inside the server's `MAX_ALERT_AGE_S` (15 minutes), so a retry shows "Sent late", never "over 15 min", when the Fob's clock is right. At most 5 alerts wait, well inside the 32 counter window.
- At most `RETRY_MAX` (5) alerts. When full, the oldest STATUS is dropped first, then the oldest SUSPICIOUS, then SILENT. A MEDICAL is never dropped to make room for a lower type. All MEDICAL: the oldest MEDICAL is dropped and the Fob says so. In general a higher type is never dropped for a lower one, so a new alert of a lower type than everything queued is not queued.
- Kept in flash (`queue.json`). Each save writes `queue.json.tmp` in full, then renames it over `queue.json`, so a power cut leaves either the old or the new queue. After a reboot, entries still inside their 10 minutes are tried again. The age comes from `ts` when the clock is set, otherwise from the age saved at the last write (time the Fob was off is not known, so this can be too young).
- A button press always wins. A retry runs only while the Fob is idle, and any button activity stops it at once (`RETRY_STOPPED`). The press is handled first. A stopped try does not count.
- When a retry gets through: the normal confirm light and buzz, except SILENT, which gets nothing at all.
- Log lines: `RETRY_QUEUED`, `RETRY_TRY`, `RETRY_DONE`, `RETRY_GAVE_UP`, `RETRY_STOPPED`, with `ctr` and `reason`. A retry's `SEND_RESULT` line ends with `try=N`.
- The server stores the press time (`ts`, the Fob's clock) next to the time the alert arrived. More than `LATE_AFTER_S` (60 s) apart: a "Sent late" tag with both times on Live, in the alert panel and in the exports. More than `MAX_ALERT_AGE_S` (15 minutes): "Sent late (over 15 min)" and a yellow warning on Settings > Health.

## Boot report (`BOOT`)

At power on the Fob checks itself, prints one line and sends a signed `BOOT` message:

```
SELF_CHECK key=ok counter=ok lora=ok gps=ok battery=ok pressure=ok wifi=ok reset=power_on fw=2026.11.11b
```

`reset` is the reset cause in a word: `power_on`, `crash`, `watchdog`, `deep_sleep`, `soft_reset` or `unknown`.

| Check | Bit in `fail` | Plain words on the dashboard |
|---|---|---|
| `key`: `SECRET_KEY` set, 32 hex characters | 1 | Secret key missing or the wrong length |
| `counter`: the counter file reads (`new` on a brand new Fob is not a failure) | 2 | Counter file could not be read |
| `lora`: the radio answers (version register 0x12) | 4 | LoRa radio not answering |
| `gps`: the wing sends data within `GPS_CHECK_MS` (5 s) | 8 | GPS not sending data |
| `battery`: the gauge reads | 16 | Battery gauge not reading |
| `pressure`: the BME280 reads | 32 | Pressure sensor not reading |
| `wifi`: joined at power on | not a bit, the `wifi` field | Information only. No WiFi is not a failure, LoRa still works |

Light: green for 1 s when every required check passed. Steady red for 3 s when any failed, then the Fob keeps running with what works. No blink counting.

Example:

```json
{"v":1,"id":"FOB-001","type":"BOOT","ctr":230,"ts":1762870000,"bat":87,
 "fail":8,"wifi":1,"fw":"2026.11.11b","rst":2,"sig":"<64 hex characters>"}
```

`rst` comes from `machine.reset_cause()`. On the ESP32 port of MicroPython 1.27, a crash (ESP-IDF `ESP_RST_PANIC`) and a software restart (`ESP_RST_SW`, `machine.reset()`) both give `2`. The Fob never calls `machine.reset()`, so the dashboard shows `2` as "Restarted after a crash". The RST button and a battery dip (brownout) both give `1` ("Power on"). Restarts are boot reports, never alerts.

It goes WiFi first, then LoRa, with the same budget as alerts, and is acked like an alert. It is not put in the retry queue. A button press stops it (`BOOT_STOPPED ctr=... reason=button`). The Fob then sends the SAME signed message later, once the press is handled and the Fob is idle (`BOOT_RESEND ctr=...`, and a `SEND_RESULT ... kind=BOOT ... resend=1` line). If the press was an alert confirmed over WiFi, the Fob is listening for help on that connection, so the BOOT report goes on the same connection and listening never stops. If that connection does not carry it, the Fob uses the normal WiFi-then-LoRa send. A BOOT report sent later that still ends unconfirmed is not tried again. The server stores it on the device (`boot_reports`, the newest 10 per device), never as an alert: it never counts toward Overview, the chart, Live, texts or exports.

## "Help is coming" (WiFi)

When staff press **Acknowledge**, the server tells the Fob a person saw the alert.

1. The server publishes to `safeping/help/<id>` at QoS 1:

   `HELP <id> <ctr> <mac>`

   `mac` = the first 16 hex characters of `HMAC-SHA256(help_key, "HELP|<id>|<ctr>")`

   `help_key` = `HMAC-SHA256(device secret_key, "safeping-help-v1")`

   `ctr` is the acknowledged alert's counter. The code is `ackcheck.help_text()`, shared by the server and the Fob.
2. The Relay never holds the help key, so a stolen Relay cannot fake "help is coming".
3. After an alert (SUSPICIOUS, MEDICAL or SILENT, not STATUS) is confirmed over WiFi, the Fob keeps that MQTT connection open for `HELP_LISTEN_MS` (2 minutes). It subscribed to `safeping/help/<id>` in the same packet as the ack topic, so this costs no extra round trip. If the broker refuses the help topic, the alert still goes out, the Fob just cannot hear help.
4. A valid help message for that `ctr`: three slow pulses (400 ms on, 400 ms off) and a slow green blink. SILENT: no buzz and no light, ever. Either way the Fob logs `HELP_RECEIVED ctr=... ms_after_confirm=...`, then disconnects.
5. Anything unsigned, wrongly signed, or for another `ctr` is ignored and logged (`HELP ignored: <reason>`).
6. Button presses work as normal while the Fob listens. A new send closes the listening connection first (one MQTT connection at a time). Alerts still inside their 2 minutes are listened for again after the next WiFi confirm.
7. The dashboard shows "Help message sent to Fob" with the time in the alert's timeline. That means the server sent it, not that the Fob got it.

Over LoRa (Part E) is not built yet.

## Message types

| Type | Meaning | Text to duty phone | Shown on dashboard |
|---|---|---|---|
| `STATUS` | 1 press, status check | no | hidden by default, logged |
| `SUSPICIOUS` | 2 presses | yes | yes |
| `MEDICAL` | 3 or more presses | yes | yes |
| `SILENT` | hold (2 s on the bench, `HOLD_MS`; the PDR said 5 s) | yes | yes |
| `REF` | Reference pressure reading | no | status strip only |
| `BOOT` | Fob self-check at power on | no | Devices page only ("Last start"), never as an alert |

## How location is decided

1. If the message has `lat` and `lon`, use them (with `acc`).
2. Otherwise, if it has `p` and the latest Reference reading is less than 120 seconds old, the floor is
   `1 + round((reference p - fob p) / PA_PER_FLOOR)`. The Reference sits on the ground floor, which the server calls floor 1.
   `PA_PER_FLOOR` defaults to 42 Pa. The floor walk on 2026-11-07 measured about 55 Pa per floor, with uneven floors (ground to 1st 68 Pa, then 54, then 42), so start the server with `PA_PER_FLOOR=55`. A per-floor table would be more accurate (planned).
3. Otherwise the alert is stored with no location.
