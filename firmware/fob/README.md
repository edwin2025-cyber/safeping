> Note (2026-11-08): `main.py` was replaced by the tested bench version. Settings are in `config.example.py` and the board file list is in the top `README.md`. Parts of this README may be out of date.

# Fob firmware

MicroPython for the Fob. `main.py` is the whole program. It follows `../../message-format.md`.

| File | What it is |
|---|---|
| `main.py` | The firmware. Copy this to the board. |
| `config.example.py` | Copy to `config.py` and fill in. `config.py` is not committed. |
| `sim_test.py` | Test for your laptop only. Do not copy it to the board. |

Related folders: `../common` holds the part drivers and the pin plan, `../bringup` holds the scripts that test each part, and `../../docs/hardware-connections.md` says what connects where.

## What it does

| Input | Alert | Light | Buzz | Sent |
|---|---|---|---|---|
| 1 press | `STATUS` | dim white while sending, then one green blink | short | right away, never texts anyone |
| 2 presses | `SUSPICIOUS` | yellow slow blink, dim yellow while sending, then solid green | one buzz | after the 2 s cancel window |
| 3 or more | `MEDICAL` | red fast blink, dim red while sending, then solid green | steady until sent | after the 2 s cancel window |
| hold 5 s | `SILENT` | none, ever | buzz only | right away |

- **Cancel window:** a quick tap during the 2 s cancels the alert and nothing is sent (green blink). Holding 5 s during the window turns it into `SILENT`. For `MEDICAL`, extra presses in the first 0.6 s count as part of the pattern and do not cancel.
- **Colors after sending:** solid green means it was confirmed. Solid orange means it was not confirmed. `SILENT` never lights the LED, even on a failure. Every color and pattern is in `docs/led-patterns.md` (red = MEDICAL, yellow = SUSPICIOUS, green = good news, orange = a problem, blue = starting up or joining WiFi).
- **Counter:** saved to `counter.txt` in flash before every send. If you erase the flash, the counter restarts at 0 and the server rejects everything as a replay until you register the Fob again.
- **Every message** is also printed to the console on a line starting with `SAFEPING_MSG`. Copy those lines into a file and run `python replay_serial.py file.txt` in the `server` folder to check them against the real server.

## Test it now, without hardware

```
python sim_test.py
```

It runs `main.py` with a fake button, clock, LED, motor and broker, then checks every message it sends against the real server code. It checks press patterns, the cancel window, SILENT escalation, counters, replays, forged messages, retries and the NeoPixel path.

Last run: 48 of 48 checks pass on desktop Python. The signing code was also run once on MicroPython 1.29 (a WebAssembly build on a laptop, not the board) and the server accepted its signature. That run is not in this repo. The first real test is on the board, see "Run it on the board" below.

## Run it on the board (when the parts arrive)

1. Wire the parts and pass every script in `../bringup`. See `../../docs/hardware-connections.md`.
2. Register the Fob on the server: `python add_device.py FOB-001 "Student Name"` (in the `server` folder). It prints a secret key.
3. Copy `config.example.py` to `config.py`. Fill in the key, the WiFi and the server's address.
4. Copy `main.py` and `config.py` to the board. Save `main.py` under that name so it runs at power on.
5. Start the server. Press the button and watch the dashboard.

## What is not written yet

These are stubs in `main.py`. Each one is a short function near the top. The drivers they will call are already written and tested in `../common`.

- `read_gps()`: call `gnss.GNSS(i2c).fix()` from `../common/gnss.py`
- `read_sensors()`: pressure and temperature from `bme280.py`, battery percent from `max17048.py`
- `lora_send()`: send the packet with `sx127x.py`
- Real-board pin numbers: confirmed on the bench with `../bringup/00_pin_walk.py`

Connect these only after the matching bring-up script passes on real hardware. When LoRa goes in, switch the message to compact JSON (no spaces), because one LoRa packet holds 255 bytes.

## Not yet tested

Real hardware, the real board's pins, and a real Mosquitto broker with real texts.
