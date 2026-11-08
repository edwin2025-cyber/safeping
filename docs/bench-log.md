# SafePing bench log

Short notes on what I tested on the real boards, what happened, and what changed.
Newest dates are at the bottom. Full test runs are in `logs/` (see `logs/README.md`).

## Current hardware (as of 2026-11-07)

| Part | Connection | Notes |
|---|---|---|
| LoRa radio (RFM95W) | SCK 10, MOSI 8, MISO 9, CS 26, RST 6. G0 not wired | VIN on 3V3 with **direct jumpers** from the board's 3V3 and GND (not through the breadboard rail), and a **100 uF capacitor** across VIN and GND at the breakout |
| Button | IO1 to GND, internal pull-up | |
| Status LED | onboard NeoPixel, IO27 | NeoPixel Mini PCB not soldered yet |
| Motor | IO3, 1 k to PN2222 base, emitter to GND, motor from 3V3 to collector, 1N4001 across the motor (stripe to 3V3) | motor wires tinned. 10 k pull-down from base to GND still to add |
| GPS wing | wing TX to IO12, wing RX to IO11, UART1 9600 | |
| I2C | SDA 23, SCL 24 (`I2C(0)`) | 0x36 battery gauge (MAX17048, on the board), 0x77 BME280 (Qwiic) |
| Battery | 3.7 V 420 mAh LiPo (label says 420, not 500) | With the LiPo plugged in, unplugging USB does not reset the board. Use RST |

## Earlier lessons (before the full Fob program)

- Lesson 1 pin walk: IO0, IO1, IO2, IO3, IO4 and IO5 all confirmed.
- Lesson 4: Fob sends, Relay receives. About 1 to 2 m apart: signal -15 to -52 dBm, 10 of 11 received.
- Indoors at 30 cm: all received, battery works, signal -6 to -52 dBm.

## 2026-11-06

- Full Fob `main.py` runs on the real board. 1 press STATUS, 2 SUSPICIOUS, 3 or more MEDICAL, hold SILENT. A quick tap in the 2 s window cancels.
- With WiFi off, every alert goes out over LoRa and the Relay reads it.
- Fixed: WiFi state error. Fixed: the Relay cut packets because it listened in 1 s windows (now 60 s).
- GPS wing wired in. Indoors it gets a fix but is 150 to 200 ft off, which is expected indoors.

## 2026-11-06 (night)

- Start checks passed. Fob `main.py` is the full program (21,663 bytes) on the board. Relay runs `relay_alert_listen.py` as `main.py`.
- Added `tests/field_log.py`. It logs both boards at once (raw, CSV, summary). Desk test: 4 of 4 received, 1 cancel sent nothing.
- Outdoor GPS (small area, practice, not the formal DT-10): fix on every press, acc 3 to 6 m, position stayed within about 1 to 3 m. Indoors it wandered about 25 m.
- Outdoors every LoRa send timed out until I replugged the Fob. Lid test and wiggle test did not reproduce it. (Solved on Nov 7: weak radio power path.)
- Found a worse bug: after `_radio.reset()` the radio goes to mode 0x09 and `lora_send()` returned True, but the Relay heard nothing. A false "sent".

## 2026-11-07

**LoRa recovery fix (on both boards)**
- `sx127x.py` checks the radio before every send and receive. `main.py` sets the radio up again and retries once. The Relay recovers by itself.
- Test A: 2 of 2 received. Test B: forced a radio reset, the Fob caught it (mode 0x09), set the radio up again and sent. The Relay heard both packets. False "sent" is fixed.

**Motor**
- Built the PN2222, 1 k, 1N4001 circuit on IO3. Some patterns did not buzz: the stranded motor wires only touched the breadboard sometimes. Tinned them, fixed.
- Chose: 100 percent strength. Sent = two 250 ms buzzes. Not sent = one 1.2 s buzz. MEDICAL pulses (200 ms on, 100 ms off) in its cancel window. No press tick (40 ms was too short to feel). STATUS keeps its single short buzz.
- I can tell sent from not sent by feel on the bench. Recheck once it is in the case.
- Bug: MEDICAL failed 3 of 3 because the motor was running during the send. Proved it in the REPL (motor on: send fails, motor off: send works). Fix: the motor is always off while sending. Then 7 of 7.

**Sensors**
- I2C scan: SDA 23, SCL 24, found 0x36 (battery gauge) and 0x77 (BME280).
- Sensor check: about 99,543 Pa, noise about plus or minus 2 Pa on the desk, lifting 1 m dropped it about 12 to 15 Pa. Battery 4,218 mV, 100 percent.
- Every alert now carries `p`, `t` and `bat`. Largest possible alert is 241 bytes (LoRa limit 255).
- With no LiPo plugged in, `bat` still says 100 percent. That number means nothing without a battery.

**Power problems and fixes**
- USB and LiPo both plugged in (charging): 3 of 5 sent. USB only: 10 of 10. LiPo only (real use): 10 of 10.
- Added a 100 uF capacitor across the radio's VIN and GND: USB and LiPo 10 of 10.
- Full run outdoors: 13 of 13 received with GPS on every alert, but 4 LoRa problems, including one `version 0x00` dropout.
- Back inside, every send failed. A register probe showed the transmit started (0x83) and dropped to sleep (0x80) within 20 ms. All settings were correct and it survived a full power cycle.
- Fix: direct 3V3 and GND jumpers from the board to the radio's VIN and GND rows. Cause: weak power path through the breadboard. Then 9 of 9 with 0 problems, including escalation to SILENT.

**Signed acks**
- The Relay saves each new alert to `queue.txt` on its flash, then sends a signed ack. The Fob resends the same message up to 3 times. Still no valid ack: NOT CONFIRMED, orange light, long buzz.
- The Relay's ack key lives only in its own `config.py` on the board and in `safeping-private`, never in git. It is made from the Fob's secret, so the Relay never holds the real secret.
- Tests: 3 of 3 confirmed on try 1. Relay unplugged: NOT CONFIRMED in about 5 s. Relay back: confirmed. Wrong key on the Relay: the Fob rejected 3 of 3 acks (bad signature). Right key back: confirmed.

**10 k pull-down**
- Added 10 k from the motor transistor's base to GND. The motor stays quiet at boot. Check run: 5 of 5 confirmed on try 1, MEDICAL pulse still works.

**Other**
- Logs moved into `logs/<date>/<time>_<label>/` with an index in `logs/README.md`.
- The Relay sometimes hears a packet that is not a SafePing alert, probably another LoRa device nearby. It ignores them.
- Thonny: pressing Stop during a running script caused a write timeout. Use Ctrl+C in the Shell instead.

**Floor walk (DT-08 practice)**
- Relay in my room (floor 3), Fob on LiPo only, phone page logged the floor and buzz for each press.
- Buzz matched the Relay 21 of 21: every short buzz was received, every long buzz was not. The ack does not lie.
- Pressure: G 99,721, floor 1 99,653, floor 2 99,599, floor 3 99,557 Pa. About 55 Pa per floor on average, but not even: G to 1 is 68 Pa, 1 to 2 is 54, 2 to 3 is 42 (tall ground floor).
- With the default 42 Pa per floor the server would get floors 1 and 3 wrong. 55 works but floor 1 is close. Better: a per-floor table on the server.
- Drift was only 2.5 Pa over 8 minutes.
- My room read about 17 Pa higher than the hallway on the same floor. Repeat this. Could be the building's air system.
- LoRa from floor 3: floor 3 7/7, floor 2 4/4, floor 1 4/5, ground 1/4 (-102 dBm, SNR -4). One Relay on floor 3 does not cover the ground floor.

## 2026-11-08

- Server from safeping-1 checked against the current Fob: same signature, replays rejected.
- No admin on the laptop: Mosquitto would not install, so I used amqtt (Python broker, installs with pip). Fake Fob to broker to server to dashboard works.
- The laptop blocks incoming connections (changing the network to Private needs admin), so the Fob cannot reach a broker on the laptop over WiFi yet.
- Added server/serial_bridge.py: the Relay's USB output goes straight into the server.
- First real end-to-end alert: Fob (real key from add_device.py) to LoRa to Relay to USB to server to dashboard. SUSPICIOUS ctr 149 and MEDICAL ctr 150 stored. Location unknown (no GPS indoors, no Reference yet).
- PA_PER_FLOOR set to 55 with an environment variable when starting app.py.

## Open items

- Repeat floor walk with more ground floor readings and a room vs hallway check.
- Formal DT-10: 3 marked outdoor spots, 5 readings each.
- `SECRET_KEY` is still the placeholder. Run `add_device.py` on the server, paste the real key, then redo the Relay's ack key.
- WiFi and server: ask IT, write the Relay forwarder that sends `queue.txt` to the server.
- Docs and CDR notes: 2 s hold (PDR says 5 s), no press tick (accessibility note says it buzzes on each press), motor off while sending, 100 uF capacitor and direct radio power, I2C pins, 420 mAh battery, final GPS module.
- NeoPixel Mini PCB, case measurements and print.
