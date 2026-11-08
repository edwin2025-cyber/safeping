# SafePing bench logs

Each run is a folder with three files from `tests/field_log.py`:

- `..._raw.txt`: every line from the Fob and the Relay, with laptop time
- `..._alerts.csv`: one row per alert (ctr), Fob side and Relay side
- `..._summary.txt`: sent, received, lost, signal and timing

New runs are saved as `logs/<date>/<time>_<label>/` automatically. Add a row here after every real test. Setup mistakes go in `archive/`.

These are bench runs, not formal DT runs yet. The "Related" column says which test or bug each one supports.

| Run | What it tested | Result | Related |
|---|---|---|---|
| [2026-11-06/215120_desk](2026-11-06/215120_desk/) | Logger check at the desk, all 4 modes plus a cancel | 4 of 4 received, cancel sent nothing, about 0.3 s Fob to Relay | DT-01, DT-02, DT-11 (support) |
| [2026-11-06/220347_spotA](2026-11-06/220347_spotA/) | Outdoor GPS practice (small area) after carrying the setup outside | GPS fix on all 8, acc 3 to 6 m, spread about 1 to 3 m. LoRa: 0 of 8, every send timed out until a replug. Cause not proven | DT-10 (practice), LoRa bug |
| [2026-11-06/221343_spotA2](2026-11-06/221343_spotA2/) | Same spot after replugging the Fob | 4 of 4 received with GPS, cancel sent nothing | DT-10 (practice) |
| [2026-11-06/222026_lidtest](2026-11-06/222026_lidtest/) | Try to reproduce the outdoor failure: laptop lid closed 30 s, then breadboard wiggle | 3 of 3 received. Neither reproduced it | LoRa bug (debug) |
| [2026-11-06/222759_resettest](2026-11-06/222759_resettest/) | Radio reset on purpose with _radio.reset() (Thonny held the Fob, logger watched the Relay) | Found the false "sent": after a reset the Fob said True but the Relay heard nothing. After begin() it worked | LoRa bug (debug) |
| [2026-11-07/183405_recovery](2026-11-07/183405_recovery/) | Test A: normal alerts with the LoRa health check and retry on both boards | 2 of 2 received, no LoRa problems | DT-11 |
| [archive/2026-11-07_183551_resetB](archive/2026-11-07_183551_resetB/) | Setup mistake: logger opened COM15 before Thonny | Not a test | archive |
| [archive/2026-11-07_183737_resetB](archive/2026-11-07_183737_resetB/) | Setup mistake: logger stopped before the Thonny commands | Not a test | archive |
| [2026-11-07/183904_resetB](2026-11-07/183904_resetB/) | Test B: radio reset on purpose with the fix | Fob caught it (mode 0x09), set the radio up again, sent. Relay heard both packets | DT-11, R6 |
| [2026-11-07/191724_motor](2026-11-07/191724_motor/) | First motor firmware (PWM, chosen patterns), all modes | MEDICAL 0 of 3 (timed out, version 0x12 mode 0x81), others 4 of 4. Cause: motor ran during the send (proven in the REPL) | DT-03, motor bug |
| [2026-11-07/192952_motor2](2026-11-07/192952_motor2/) | Motor off while sending, no press tick. 3 MEDICAL, then all modes, then radio VIN pulled | 7 of 7 received. VIN pulled: honest NOT SENT with version 0x00, recovered after VIN went back | DT-03, DT-11 |
| [2026-11-07/195511_sensors](2026-11-07/195511_sensors/) | BME280 and battery gauge in every alert. LiPo and USB both plugged in | p, t, bat in every alert. LoRa 3 of 5 (2 timed out, version 0x12 mode 0x81) | DT-08 (support), power bug |
| [2026-11-07/195950_nolipo](2026-11-07/195950_nolipo/) | Same firmware, LiPo unplugged, USB only, 10 STATUS | 10 of 10 received. bat read 100 percent with no LiPo (meaningless) | power bug (debug) |
| [2026-11-07/200408_lipoonly](2026-11-07/200408_lipoonly/) | Battery only, no USB on the Fob (real use). 10 STATUS. Relay side only | 10 of 10 received (ctr 72 to 81, no gaps) | DT-11, R5 |
| [2026-11-07/201424_cap](2026-11-07/201424_cap/) | 100 uF capacitor across the radio VIN and GND. LiPo and USB both in (the setup that failed) | 10 of 10 received, bat 97 percent | power fix |
| [2026-11-07/202833_fullfob](2026-11-07/202833_fullfob/) | Full Fob run outdoors, all modes plus cancel and escalation, LiPo and USB | 13 of 13 received, GPS on all, 4 LoRa problems (2 recovered on retry), one version 0x00 dropout | power bug |
| [2026-11-07/212450_fullfob2](2026-11-07/212450_fullfob2/) | Same run after direct 3V3 and GND jumpers to the radio | 9 of 9 received, 0 LoRa problems, escalation to SILENT worked | DT-01, DT-02, DT-11, power fix |
| [2026-11-07/214928_ack](2026-11-07/214928_ack/) | Signed acks: 3 normal, Relay unplugged, Relay back | 3 of 3 confirmed on try 1; Relay off gave NOT CONFIRMED in about 5 s; confirmed again after | DT-11, R6 |
| [2026-11-07/215409_ackfake](2026-11-07/215409_ackfake/) | Relay given a wrong ack key on purpose | Fob rejected 3 of 3 acks (bad signature), NOT CONFIRMED, Relay still stored it | DT-04 style, cyber |
| [2026-11-07/215521_ackfixed](2026-11-07/215521_ackfixed/) | Correct ack key put back | Confirmed on try 1 | DT-11 |
| [2026-11-07/220846_pulldown](2026-11-07/220846_pulldown/) | Check after adding the 10 k pull-down on the motor transistor | 5 of 5 confirmed on try 1 | DT-03, DT-11 |
| [2026-11-07/222238_floorwalk](2026-11-07/222238_floorwalk/) | Floor walk from floor 3 down to G and back, Fob on LiPo, phone floor page | Buzz matched Relay 21 of 21. About 55 Pa per floor (68, 54, 42). Ground floor 1 of 4 heard | DT-08, DT-11 |

## What these runs showed (2026-11-06 and 2026-11-07)

- LoRa from the real Fob to the Relay works in all four modes, about 0.3 s from the Fob print to the Relay print.
- The radio driver could report "sent" after a radio reset when nothing was sent. Fixed with a health check before every send and one retry.
- The motor running during a send stalls the radio. Fixed: the motor is always off while sending.
- With USB and the LiPo both plugged in (charging), sends failed 2 of 5. Battery only: 10 of 10. A 100 uF capacitor across the radio's VIN and GND: 10 of 10 with USB and LiPo. The radio is fed from the board's 3V3.
- GPS outdoors: fix on every press, position stable to about 1 to 3 m (practice run, not the formal DT-10 yet).
