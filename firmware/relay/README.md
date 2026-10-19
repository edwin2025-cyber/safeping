# Relay firmware (MicroPython)

The Relay passes Fob alerts from LoRa on to the server. This folder holds its MicroPython code.

What it will do (see [message-format.md](../../message-format.md)):

- Listen for LoRa packets from Fobs.
- Connect to WiFi and the MQTT broker.
- Publish each packet to `safeping/alerts` exactly as received. It does not edit or re-sign anything, so the server cannot tell which path a message took.

## Setup

Copy `config.example.py` to `config.py` and fill in the real values. `config.py` is ignored by git.
