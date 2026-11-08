# Relay

Sits by a third floor window (USB power), listens for Fob alerts over LoRa, saves each one, and answers with a signed ack.

## Files on the board

- `main.py` = `firmware/relay/main.py` (it started as `tests/relay_alert_listen.py` in the bench repo)
- `sx127x.py` and `ackcheck.py` from `firmware/lib/`
- `config.py` with `ACK_KEYS` (see `config.example.py`). Never in git.

## What it does now

1. Listens continuously (60 s receive windows, so a packet is never cut off).
2. A new SafePing alert is stored in `queue.txt` on the board, then acked: `ACK <id> <ctr> <mac>`.
3. Prints the alert as `SAFEPING_MSG <json>` over USB. `server/serial_bridge.py` reads those lines into the server.
4. A resent alert (same id and ctr) is acked again but printed only as `duplicate of ...`.
5. If the radio resets or stops answering, it sets the radio up again and keeps listening.

## Not done yet

- Forwarding `queue.txt` to the MQTT broker over WiFi (needs a network the boards can use).
- Emptying `queue.txt` once the server has an alert.

## Tested

See `logs/README.md`: ack, ackfake, ackfixed and floorwalk runs (2026-11-07), and the first end-to-end alert through the serial bridge (2026-11-08).
