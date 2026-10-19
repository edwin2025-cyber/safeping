# Reference firmware (MicroPython)

The Reference is a fixed device on the ground floor that measures the baseline air pressure. This folder holds its MicroPython code.

What it will do (see [message-format.md](../../message-format.md)):

- Read the air pressure (and temperature if available) on a regular schedule.
- Send a signed `REF` message with `p` in pascals to `safeping/reference` over WiFi and MQTT. It signs with its own secret key, the same way a Fob does.
- Keep its counter going up with every message.

The server compares a Fob's pressure with the latest Reference reading (if it is under 120 seconds old) to work out which floor an alert came from.

## Setup

Copy `config.example.py` to `config.py` and fill in the real values. `config.py` is ignored by git. Get the device's secret key by running `add_device.py REF-01 --role REF` on the server.
