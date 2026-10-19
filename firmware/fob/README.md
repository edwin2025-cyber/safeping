# Fob firmware (MicroPython)

The Fob is the device a student carries. This folder holds its MicroPython code.

What it will do (see [message-format.md](../../message-format.md)):

- Read button presses and turn them into a message type: 1 press is `STATUS`, 2 presses is `SUSPICIOUS`, 3 or more is `MEDICAL`, and holding for 5 seconds is `SILENT`.
- Build the message with integer fields (`v`, `id`, `type`, `ctr`, and `lat`, `lon`, `acc`, `p`, `t`, `bat` when it has them).
- Sign the message with HMAC-SHA256 using the Fob's own secret key, in the field order the format defines.
- Send it to `safeping/alerts` over WiFi and MQTT, or over LoRa to a Relay.
- Save the counter to flash after every send, so a restart never reuses an old value.
- Never send a student name. Names live only on the server.

## Setup

Copy `config.example.py` to `config.py` and fill in the real values. `config.py` is ignored by git. Get the device's secret key by running `add_device.py` on the server.
