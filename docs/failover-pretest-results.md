# Failover pre-test: "before" results (current firmware)

**Date:** Nov 10, 2026, 22:43 to 22:52
**Setup:**
- The Fob (COM15) and the Relay (COM14) were both on USB at the desk, indoors, with no GPS fix.
- The logger recorded both boards: `field_log.py --label failover_pre_tN`.
- 3 SUSPICIOUS presses per test.
- **Timing is from the logger's timestamps:**
  - **Total** = the press buzz (`[VIBRATE: one]`) to the result buzz.
  - **Send** = `SAFEPING_MSG` to the result buzz.

## Results

| Test | Setup | Press | Total (s) | Send (s) | Path | Result buzz |
|---|---|---|---|---|---|---|
| 1 | WiFi off (`"none"`) | 1 | 2.6 | 0.5 | LoRa | confirm |
| 1 | | 2 | 2.5 | 0.4 | LoRa | confirm |
| 1 | | 3 | 2.5 | 0.4 | LoRa | confirm |
| 2 | Made-up WiFi name | 1 | 4.1 | 2.0 | WiFi failed after 1.5 s, then LoRa | confirm |
| 2 | | 2 | 4.0 | 1.9 | same | confirm |
| 2 | | 3 | 4.3 | 2.3 | same | confirm |
| 3 | Real WiFi, broker unreachable | 1 | 6.4 | 4.3 | WiFi refused at once, LoRa: **Relay got it, all 3 acks missed** | **fail (false)** |
| 3 | | 2 | 2.5 | 0.4 | WiFi refused at once, then LoRa | confirm |
| 3 | | 3 | 2.5 | 0.4 | same | confirm |
| 4 | Made-up WiFi name, Relay unplugged | 1 | 7.9 | 5.8 | WiFi failed, LoRa, no ack | fail (correct) |
| 4 | | 2 | 7.8 | 5.7 | same | fail (correct) |
| 4 | | 3 | 7.8 | 5.7 | same | fail (correct) |

The buzzes felt by hand matched the log in all 12 presses.

## What we learned

1. **LoRa only is fast:** about 0.4 s from send to confirm.
2. **About 2 s pass before every send even starts.** The press buzz comes about 2 s before `SAFEPING_MSG`, on every press. This includes the multi-press window and the "no GPS fix" check. It is the biggest delay on the good path. To investigate in the firmware pass.
3. **A wrong WiFi name costs about 1.5 s** with the current settings: one join attempt, then LoRa. Not the 30 s worst case from the code review, because the real config uses shorter values than the defaults.
4. **There was no hang.** The broker address refused the connection right away (`ECONNRESET`), so the "no time limit" case was not triggered. It stays a risk for an address that never answers. The firmware pass fixes it and adds a test for it.
5. **One false "fail"** (test 3, press 1): the Relay received the alert and acked it 3 times, but the Fob heard none of the acks. The alert was delivered, but the wearer was told it failed. That is the safe kind of mistake (they would press again), but it should not happen. A likely cause is WiFi activity right before the LoRa receive window. The firmware pass makes WiFi go idle during LoRa sends.
6. **No false "confirmed"** in any test. With the Relay unplugged, every press gave the fail buzz, after about 7.8 s.
7. **An error line on every press with a wrong WiFi name** (`wifi:sta is connecting, cannot set config`): the board keeps trying to join in the background. Harmless, but to be cleaned up.

## Run folders

`logs/2026-11-10/224354_failover_pre_t1`, `224609_failover_pre_t2`, `224821_failover_pre_t3`, `225040_failover_pre_t4`.
