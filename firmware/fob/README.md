# Fob firmware

MicroPython for the Fob. `main.py` is the whole program. It follows `../../message-format.md`.

| File | What it is |
|---|---|
| `main.py` | The firmware. Upload this. |
| `config.example.py` | Copy to `config.py` and fill in. `config.py` is not committed. |
| `sim_test.py` | Test for your laptop only. Do not upload it. |

## What it does

| Input | Alert | Light | Buzz | Sent |
|---|---|---|---|---|
| 1 press | `STATUS` | white blink | short | right away, never texts anyone |
| 2 presses | `SUSPICIOUS` | yellow slow blink, then solid yellow | one buzz | after the 2 s cancel window |
| 3 or more | `MEDICAL` | red fast blink, then solid red | steady until sent | after the 2 s cancel window |
| hold 5 s | `SILENT` | none, ever | buzz only | right away |

- **Cancel window:** a quick tap during the 2 s cancels the alert and nothing is sent (green blink). Holding 5 s during the window turns it into `SILENT`. For `MEDICAL`, extra presses in the first 0.6 s count as part of the pattern and do not cancel.
- **Colors after sending:** solid color means the broker accepted the message. Solid orange means it could not be sent. `SILENT` never lights the LED, even on a failure. It buzzes three times instead.
- **Counter:** saved to `counter.txt` in flash before every send. If you erase the flash, the counter restarts at 0 and the server rejects everything as a replay until you register the Fob again.
- **Every message** is also printed to the console on a line starting with `SAFEPING_MSG`.

## Run it in Wokwi

1. Make an ESP32 MicroPython project. Put in `main.py`, `config.py` (from `config.example.py`) and `umqtt/simple.py`.
2. Wire these parts:

   | Part | Pin |
   |---|---|
   | Pushbutton, other leg to GND | GPIO 0 |
   | RGB LED (common cathode, common leg to GND), red / green / blue | GPIO 2 / 4 / 5 |
   | LED + resistor to GND, stands in for the vibration motor | GPIO 18 |

3. On the server, register the Fob with the key you put in `config.py`:
   `python add_device.py FOB-001 "Student Name" --key <SECRET_KEY>`
4. Run it and press the button. Copy the console text into `serial.txt`, then:
   `python replay_serial.py serial.txt` (in the `server` folder). Each message shows as accepted or rejected, the same as a live one.

Wokwi cannot reach a broker on your laptop, so the replay step is how Wokwi output gets to the real server.

## What is not written yet

These are stubs in `main.py`. Each one is a short function near the top.

- `read_gps()`: GPS, when the module arrives
- `read_sensors()`: BME280 pressure and temperature, and the battery percent
- `lora_send()`: the LoRa fallback when WiFi fails
- Real-board pin numbers: set after the GPIO plan is final

## Test it on your laptop

```
python sim_test.py
```

It runs `main.py` with a fake button, clock, LED, motor and broker, then checks every message it sends against the real server code. It checks press patterns, the cancel window, SILENT escalation, counters, replays, forged messages, retries and the NeoPixel path.

Last run: 48 of 48 checks pass. The signing code was also run on a real MicroPython build, and the server accepted its signature. Not yet tested: real hardware, Wokwi itself, and the real board's pins.
