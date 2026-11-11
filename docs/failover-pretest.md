# Failover pre-test: WiFi first, LoRa backup ("before" measurements)

**Goal:** measure what the Fob does today when WiFi is broken in different ways:
- Which path delivers the alert?
- How long does each press take?
- Does it ever get stuck?

These are the **"before"** numbers. After the firmware fixes, we run the same tests again for the **"after"** numbers.

**Where:** indoors at the desk, with the Fob and the Relay both on USB. This is not a range test.

**Today's firmware behavior (from the code review, Nov 9):**
- WiFi/MQTT is always tried first, 3 times. LoRa is used only after all 3 fail.
- A failed WiFi join costs up to 3 x `WIFI_TIMEOUT_MS` before LoRa.
- **If WiFi joins but the broker does not answer, there is no time limit.** The Fob may hang and never use LoRa.
- STATUS result buzz: one short 150 ms buzz = sent, one long 1.2 s buzz = failed.

## Setup (once)

1. Plug in the **Relay** (COM14) and the **Fob** (COM15). Open nothing else on those ports. Start the logger first, before Thonny, to avoid a port conflict.
2. Start the logger **with** the Fob, so the log shows which path the Fob used:
   ```
   cd $HOME\Documents\safeping
   ```
   ```
   python tests\field_log.py --label failover_pre
   ```
   (No `--no-fob` this time.)
3. Keep a phone stopwatch ready. For each press, time from **the end of the press** to **the result buzz**. The log has no durations yet, so the stopwatch is the measurement.
4. Use **SUSPICIOUS** presses (2 quick presses). That gives the clearest result buzz. No server is running, so nothing gets texted.

To change a config value between tests:
1. Stop the logger with Ctrl+C.
2. Open Thonny. Press Ctrl+C in the Shell (not the Stop button).
3. Edit the Fob's `config.py` and save.
4. Close Thonny. Press the Fob's **RST** button.
5. Start the logger again with a new label (for example `failover_pre_t2`).

Write down the values you change (`WIFI_SSID` on or off, and the `MQTT_HOST` setting) by name only, not the passwords.

## The tests

Do **3 presses** per test, about 20 seconds apart.

| # | Setup | What should happen | Record |
|---|---|---|---|
| 1 | **LoRa only:** `WIFI_SSID = "none"` | LoRa, confirm buzz, fast (the baseline) | seconds per press, buzz, path in log |
| 2 | **No such network:** `WIFI_SSID` set to a made-up name, like `"nope-test"` | The WiFi join fails, then LoRa. **Expect a long delay.** | the same |
| 3 | **WiFi works, broker unreachable:** the real school WiFi name and password, with `MQTT_HOST` left at whatever it is now (your laptop, which the firewall blocks) | Unknown. It may fall back to LoRa after a while, **or hang**. | the same. **If there is no buzz after 60 s, write "HANG", press RST, and move on.** |
| 4 | **Nothing works:** the same as test 2, **and unplug the Relay's USB** | Fail buzz. No false "confirmed". | the same |

After test 4, plug the Relay back in.

## Record sheet

| Test | Press | Seconds to buzz | Buzz (confirm / fail / none) | Path in log (MQTT / LoRa / none) | Notes |
|---|---|---|---|---|---|
| 1 | 1 | | | | |
| 1 | 2 | | | | |
| 1 | 3 | | | | |
| 2 | 1 | | | | |
| 2 | 2 | | | | |
| 2 | 3 | | | | |
| 3 | 1 | | | | |
| 3 | 2 | | | | |
| 3 | 3 | | | | |
| 4 | 1 | | | | |
| 4 | 2 | | | | |
| 4 | 3 | | | | |

**How to read the log:**
- **MQTT used:** `sent <kind> ctr <n>`, with no "LoRa" in the line.
- **LoRa used:** `send attempt N failed: ...` lines, then `sent over LoRa ... confirmed by the Relay`, `NOT CONFIRMED` or `NOT SENT`.
- **Hang:** nothing printed after `SAFEPING_MSG`.

## After

1. Stop the logger. Unplug the LiPo if it is attached.
2. **Set the Fob back to `WIFI_SSID = "none"`** (LoRa only) until the firmware fixes are in.
3. Send Claude the log folders and the filled-in record sheet.

## What we expect to learn

- Test 1 sets the baseline delivery time.
- Tests 2 and 3 show how much time a broken WiFi path adds before LoRa. This is the delay the firmware fixes must remove (target: no more than about 5 s extra).
- Test 3 tells us whether the "no time limit on the broker" risk is real on this board.
- Test 4 checks that the Fob never claims success when nothing got through.
