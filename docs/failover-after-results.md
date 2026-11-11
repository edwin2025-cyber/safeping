# Failover tests: after results

Date: Nov 11, 2026
Firmware: second WiFi fix (StepError fix, WiFi fully off before LoRa, real error reasons)
Setup: Fob and Relay on USB, indoors, field logger running. 3 SUSPICIOUS presses per test, about 30 s apart.

`ms` is from the start of the send to the result. It starts after the 2 s SUSPICIOUS cancel window.

## Results

| Test | What was broken | Path used | Result | Reason given | Time (ms) |
|---|---|---|---|---|---|
| Quick check | Nothing | WiFi | 2 of 2 confirmed | - | 1358 to 2460 |
| 3 | Broker address never answers (10.255.255.1) | LoRa | 3 of 3 confirmed | connect_timeout | 5586 to 5831 |
| 4 | Server stopped | LoRa | 3 of 3 confirmed | no_server_ack | 4711 to 5620 |
| 5 | Made-up WiFi name | LoRa | 3 of 3 confirmed | wifi_join_failed | 672 to 804 |
| 6 | CA file missing | LoRa | 3 of 3 confirmed | ca_missing | 499 to 813 |
| 7 | Relay unplugged and made-up WiFi name | LoRa | 3 of 3 not confirmed, long fail buzz felt each time | wifi_join_failed, then no LoRa ack | 4463 to 4605 |
| Normal | Nothing (after all tests) | WiFi | 2 of 2 confirmed | - | 1412 to 3508 |

Totals: 20 presses. 17 confirmed, 3 correctly not confirmed. 0 false confirms. 0 crashes. 0 lost alerts while a path was working.

## Before and after

| What | Before | After |
|---|---|---|
| Crash on WiFi error (ctr 207, `Exception.__init__`) | Yes | None in 20 presses |
| LoRa radio stall after WiFi ("setting the radio up again") | Yes, 7.8 s total | Never seen |
| Made-up WiFi name | 4.1 s | 0.7 to 0.8 s |
| Nothing works (fail buzz) | about 7.8 s | about 4.5 s |
| Error reason in the log | Wrong or missing | Real reason every time |

## Problems found

1. **`Wifi Internal State Error`** on ctr 221 (test 5) and ctr 228 (test 7). Both came after several failed joins in a row. The fallback still worked. It did not show up in the normal check afterward. Risk: right after a fallback, a press could skip WiFi even when WiFi is there. Fix planned.
2. **LoRa confirm means the Relay got it, not the server.** During the tests the logger held the Relay's port, so the bridge was off. The Fob still got confirms, but the website showed nothing. In normal use the bridge runs. Feature 1 ("help is coming" buzz) covers this gap.
3. **The broker did not hold WiFi alerts while the server was down** (test 4). The LoRa fallback covers this. Planned improvement: the server keeps its MQTT session so the broker holds messages while it restarts.
4. **Logger summary** counts only LoRa confirms, so WiFi confirms show "0 of 0." It also keeps trying COM14 when `--relay` is left out. Both are logger fixes, not Fob problems.

## Log folders

`logs/2026-11-11/`: `122033_after_quick`, `122708_after_t3`, `123159_after_t4`, `123613_after_t5`, `123946_after_t6`, `124342_after_t7`, `125433_after_normal`
