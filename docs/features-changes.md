# New features: replay rule, boot self-check, retry queue, "help is coming"

Date: Nov 11, 2026
Parts done: A, B, C, D, then the follow-up (section 7). Part E (help over LoRa) is not started.
The message rules are in `docs/message-format.md`. That file was changed first.

Note: the follow-up in section 7 replaced Part A's "stale" rule with a counter window. Where sections 1 to 6 say "stale", section 7 is what the code does now.

## 1. What changed, by file

### Part A: replay and duplicate rule (server)

| File | Change |
|---|---|
| `server/validate.py` | New counter rule in `check_counter()`: duplicate (same counter, same signature, any age), accepted (unseen counter, `ts` within 900 s), replay (same counter, different message), stale (unseen counter, `ts` too far off). No `ts`: the old "must be higher" rule. REF keeps the old rule. `authenticate()` takes `now`. Also: the `BOOT` type, its 3 extra signed fields and their checks, and `boot_failures()` (plain words) |
| `server/db.py` | `accepted_sigs` is now the record of seen counters, with a unique index on (device, counter) so two copies can never both be stored. New: `seen_sig`, `claim_counter`, `release_counter`, `raise_counter`, `prune_seen`. Removed: `record_accepted`, `is_recent_duplicate`. New tables `boot_reports` and `help_sent` and their functions |
| `server/processor.py` | Uses the new reasons. Duplicates are acked again. A message that cannot be saved gives its counter back. Prunes seen counters older than 7 days, at most once an hour. Stores `BOOT` as a boot report, never as an alert. Returns `late` for alerts |
| `server/config.py` | New: `MAX_ALERT_AGE_S` (900), `SEEN_KEEP_DAYS` (7), `BOOT_REPORTS_KEPT` (10), `LATE_AFTER_S` (60), `TOPIC_HELP_PREFIX`. Removed: `DUPLICATE_WINDOW_S` (the 10 minute window is gone) |
| `server/test_duplicates.py` | 31 checks before, 50 now. Out-of-order real alerts accepted, old exact copy is a duplicate, changed message with a used counter is a replay, too-old and clock-ahead alerts are stale, the rule survives a restart, pruning. Two old checks changed on purpose: an identical copy after 10 minutes, and a held WiFi copy after 10 minutes, are now `duplicate` instead of `replay`. That is the new rule 1 |
| `server/test_attacks.py` | 16 checks before, 19 now. The 10 replayed copies are now logged as `duplicate` (still rejected, still 30 rejections logged). New: changed message with a used counter is replay, a captured alert played back an hour later is stale |

### Part B: boot self-check and boot report

| File | Change |
|---|---|
| `firmware/lib/selfcheck.py` (new) | The checks' rules, the fail bits, the `SELF_CHECK` line and the `BOOT` message |
| `firmware/fob/main.py` | `self_check()`, `show_check()` (green 1 s or steady red 3 s), `send_boot_report()`. `FW_VERSION = "2026.11.11"`. BOOT signing adds `fail`, `wifi`, `fw` |
| `server/app.py` | `/api/devices` has `last_boot`. New `/api/devices/<id>/boots` (newest 10) |
| `tests/field_log.py` | Records `SELF_CHECK` and BOOT messages (BOOT is kept out of the alert counts). Summary lines: Self-check, Boot reports |
| `dashboard/src/components/DevicesPage.jsx` | "Last start" column: how long ago, then "All checks passed" or the failed parts in orange |
| `dashboard/src/components/DevicePeek.jsx` | "Starts and self-checks" section: last start, result, WiFi (as information), firmware, and the last 10 starts |
| `dashboard/src/App.jsx` | Loads a device's boot reports while its panel is open |
| `dashboard/src/mock/api.js`, `mock/data.js` | Boot reports in mock mode (`MOCK_BOOTS`) |
| `tests/test_selfcheck.py` (new) | 39 checks |

### Part C: retry queue

| File | Change |
|---|---|
| `firmware/lib/retryq.py` (new) | The queue: drop order, 30 s spacing, give up after 10 minutes, safe save to flash (`.tmp` then rename), resume after a reboot |
| `firmware/lib/presslog.py` (new) | Button edges recorded by a hardware interrupt, and the same debounce rule as before. Presses during a slow call are no longer lost and keep their real times |
| `firmware/fob/main.py` | `deliver()` (one WiFi-then-LoRa send, used by alerts, retries and BOOT), `queue_retry()`, `run_retries()`, `resume_queue()`. `step()` now handles each press and release at the time it happened. Any button activity stops a retry (`PressStop`). Retry confirm: normal light and buzz, SILENT nothing |
| `firmware/lib/sendpath.py` | `mqtt_attempt()` takes `stop` (time left becomes 0 on a press) |
| `firmware/lib/sx127x.py` | `receive()` takes an optional `stop`, so the LoRa ack wait ends on a press. Old callers are unchanged |
| `server/app.py`, `server/stats.py` | Alerts have `pressed_at`, `late_s`, `sent_late`. CSV has "Pressed (Fob clock)" and "Sent late" |
| `dashboard/src/components/Tags.jsx` | `LateTag`: gray "Sent late" with both times in the tooltip |
| `dashboard/src/components/AlertTable.jsx`, `AlertPeek.jsx`, `DevicePeek.jsx` | The tag on Live rows, in the alert panel (Pressed card and timeline) and in the device history |
| `dashboard/src/lib/exportXlsx.js` | The two new columns in the Excel export |
| `tests/field_log.py` | Records `RETRY_*` lines. A retry's `SEND_RESULT` no longer overwrites the first result. Summary: queued, tries, got through, gave up, still waiting, stopped by a press. CSV columns `retry_tries`, `retry_result` |
| `tests/fakeboard.py` (new) | Fake `machine`, `network` and `neopixel`, so the real `main.py` runs on the laptop |
| `tests/test_retry_queue.py` (new) | 71 checks |

### Part D: help is coming (WiFi)

| File | Change |
|---|---|
| `firmware/lib/ackcheck.py` | `help_key()`, `help_text()`, `check_help()` (shared by server and Fob) |
| `firmware/lib/helplisten.py` (new) | Listens without blocking, pings every 20 s (not while the motor runs), times out after 2 minutes, logs every ignored message |
| `firmware/lib/umqtt_safe.py` | `subscribe_many()` (ack and help topics in one packet, a refused topic does not raise) and `ping()` |
| `firmware/lib/sendpath.py` | `mqtt_attempt()` takes `help_topic` and `keep_open`. A refused help topic never stops the alert |
| `firmware/fob/main.py` | Keeps the connection after a WiFi confirm (SUSPICIOUS, MEDICAL, SILENT). Help: three slow pulses and a slow green blink. SILENT: nothing |
| `server/mqtt_listener.py` | `help_for()`, `send_help()` |
| `server/app.py` | Acknowledge sends the help message and records it. Alerts have `help_sent_at` |
| `dashboard/src/components/AlertPeek.jsx` | "Help message sent to Fob" with the time in the timeline |
| `dashboard/src/mock/api.js` | Acknowledge in mock mode sets `help_sent_at` |
| `tests/field_log.py` | Records `HELP_*` lines. Summary: help received, ms after the confirm, timeouts, ignored. CSV column `help_ms` |
| `tests/test_help.py` (new) | 49 checks |

### Shared and docs

| File | Change |
|---|---|
| `firmware/fob/config.example.py` | `RETRY_EVERY_MS`, `RETRY_FOR_MS`, `RETRY_MAX`, `HELP_LISTEN_MS`, and notes on `QUEUE_FILE`, `GPS_CHECK_MS`, `SECRET_KEY_LEN` |
| `dashboard/src/components/SettingsModal.jsx` | `stale` is a reason ("too old (stale)") and turns Rejected messages red. The Duplicates caught text now says what a duplicate is |
| `dashboard/src/lib/icons.js`, `alertMeta.js`, `components/live.css` | Two icons, `isSentLate()`, styles for the new tag and column |
| `tests/test_wifi_errors.py` | The MicroPython exception check now also reads the 5 new and changed lib files |
| `docs/message-format.md` | Counters, duplicates and replays. When the Fob has no clock. Retry queue. Boot report. Help is coming. BOOT fields and signing |
| `docs/how-to-run.md` | Test counts, the new laptop tests, the new log lines, EMQX permissions |
| `docs/dashboard.md` | Sent late, help in the timeline, Last start, starts section, stale, API and export columns, mock data |

## 2. Test results (laptop, Nov 11, 2026)

| Test | Result |
|---|---|
| `server/test_attacks.py` | 19 of 19 |
| `server/test_duplicates.py` | 58 of 58 (after the follow-up) |
| `tests/test_sendpath.py` | 37 of 37 (unchanged) |
| `tests/test_wifi_errors.py` | 58 of 58 (53 before, 5 new file checks) |
| `tests/test_retry_queue.py` | 71 of 71 |
| `tests/test_help.py` | 51 of 51 (after the follow-up) |
| `tests/test_selfcheck.py` | 39 of 39 |
| `npm.cmd run build` | builds (the old "chunk larger than 500 kB" warning only) |
| `npm.cmd run contrast` | all pairs pass |

Nothing was run on a board. The dashboard was built but not looked at in a browser.

## 3. Copy to the Fob (Thonny, board paths)

| Laptop file | Board path | New or changed |
|---|---|---|
| `firmware/fob/main.py` | `/main.py` | changed |
| `firmware/lib/sendpath.py` | `/sendpath.py` | changed |
| `firmware/lib/umqtt_safe.py` | `/umqtt_safe.py` | changed |
| `firmware/lib/ackcheck.py` | `/ackcheck.py` | changed |
| `firmware/lib/sx127x.py` | `/sx127x.py` | changed |
| `firmware/lib/presslog.py` | `/presslog.py` | new |
| `firmware/lib/retryq.py` | `/retryq.py` | new |
| `firmware/lib/selfcheck.py` | `/selfcheck.py` | new |
| `firmware/lib/helplisten.py` | `/helplisten.py` | new |

Unchanged on the Fob: `/gps.py`, `/bme280.py`, `/max17048.py`, `/certs/broker-ca.pem`, `/config.py`.
The Fob will not start if one of the 4 new files is missing (it stops with an ImportError at the top). That is on purpose, like `sendpath.py`.

The Relay needs nothing new for Parts A to D. Its `ackcheck.py` and `sx127x.py` changes only add things.

The Fob creates `/queue.json` (and briefly `/queue.json.tmp`) by itself.

### Config lines to add by hand

None are required. Every new setting has a default in `main.py`. To change them, add to the Fob's `config.py`:

```
RETRY_EVERY_MS = 30000
RETRY_FOR_MS = 600000
RETRY_MAX = 5
HELP_LISTEN_MS = 120000
```

For the give-up test below, `RETRY_FOR_MS = 120000` makes it 2 minutes instead of 10. Put it back after.

The server needs no new environment variables. Optional: `MAX_ALERT_AGE_S` (900) and `SEEN_KEEP_DAYS` (7). Restart `app.py` and `serial_bridge.py` so they use the new code. The database gets its new tables and index by itself at start.

## 4. EMQX permission changes

In the EMQX console, Access Control > Authorization:

| User | Action | Topic |
|---|---|---|
| `safeping-fob` | subscribe | `safeping/help/${clientid}` |
| `safeping-server` | publish | `safeping/help/#` |

The Fob's MQTT client id is its device id (`FOB-001`), so `${clientid}` lets each Fob hear only its own help messages. All Fobs share the user name `safeping-fob`, so do not use `${username}`. If you prefer fixed rules, use `safeping/help/FOB-001`, one rule per Fob.

Until this is done, alerts work exactly as before. The Fob prints "help topic refused by the broker (EMQX permission), no help buzz this time".

## 5. Board test plan (Parts B, C and D)

Run the logger with both boards on USB: `python tests\field_log.py --label NAME --relay COM14 --forward`, and the server with MQTT on (how-to-run section 8). `--forward` lets the website show LoRa alerts while the logger holds the Relay port.

### Part B: self-check (label `selfcheck`)

| # | Do | Expect |
|---|---|---|
| B1 | Everything attached, press RST | Green for 1 s. `SELF_CHECK key=ok counter=ok lora=ok gps=ok battery=ok pressure=ok wifi=ok fw=2026.11.11`. A BOOT `SAFEPING_MSG`, then `SEND_RESULT ... kind=BOOT ... result=confirmed`. Devices page: Last start "just now", "All checks passed" |
| B2 | Unplug the BME280 (Qwiic), press RST | Steady red for 3 s, `pressure=fail`. Devices: "1 problem: Pressure sensor not reading". Then a SUSPICIOUS press still works |
| B3 | GPS wing off (or its TX wire out), press RST | Red, `gps=fail`, "GPS not sending data" |
| B4 | `WIFI_SSID = "none"`, press RST | `wifi=off`, still green. BOOT goes over LoRa |
| B5 | Press the button during the red light in B2 | The press is handled after the boot report (or stops it: "BOOT report stopped by a button press") |
| B6 | Open the Fob on the Devices page | Starts and self-checks lists B1 to B4 |

### Part C: retry queue (label `retry`)

| # | Do | Expect |
|---|---|---|
| C1 | Relay unplugged and a made-up WiFi name (like failover test 7). One SUSPICIOUS press | Fail buzz. `RETRY_QUEUED ctr=N kind=SUSPICIOUS reason=wifi_join_failed queue=1` |
| C2 | Wait 30 s | `RETRY_TRY ctr=N ... try=1`, then a `SEND_RESULT ... try=1` with `not_confirmed`. No buzz |
| C3 | Plug the Relay back in, wait for the next try | `RETRY_DONE ctr=N ... path=lora`, the normal confirm (yellow and two pulses). Website: the alert with "Sent late", both times in the tooltip |
| C4 | As C1, but hold for SILENT, then plug the Relay in | `RETRY_DONE` with no buzz and no light |
| C5 | As C1, then watch for `RETRY_TRY` and tap once right away | `RETRY_STOPPED ctr=N try=... reason=button`, then the tap is sent as a STATUS at once. The entry is tried again about 5 s later |
| C6 | As C1, then press RST within 10 minutes | After the self-check: `RETRY_QUEUED ... reason=resumed_after_reboot` |
| C7 | As C1 with `RETRY_FOR_MS = 120000`, leave the Relay out | `RETRY_GAVE_UP ctr=N ... reason=timeout` after 2 minutes |
| C8 | 6 failed presses in a row (mixed types) | When full, the oldest STATUS goes first (`RETRY_GAVE_UP ... reason=queue_full`). Never a MEDICAL for a lower type |

Logger summary: Retry queue lines (queued, tries, got through, gave up, stopped by a press).

### Part D: help is coming (label `help`). EMQX rules first.

| # | Do | Expect |
|---|---|---|
| D1 | WiFi working. One SUSPICIOUS press | WiFi confirm, then `HELP_LISTEN ctr=N kind=SUSPICIOUS ms=120000` |
| D2 | Within 2 minutes, press Acknowledge on the dashboard | Fob: three slow pulses and a slow green blink. `HELP_RECEIVED ctr=N ms_after_confirm=...`. Dashboard timeline: "Help message sent to Fob" with the time |
| D3 | Hold for SILENT, then Acknowledge | `HELP_RECEIVED`, no buzz and no light |
| D4 | Press, do not acknowledge for 2 minutes | `HELP_TIMEOUT ctr=N ms=120000`. Acknowledging after that: nothing on the Fob, the timeline still says "sent" |
| D5 | After D1, tap once (STATUS), then Acknowledge the first alert | The STATUS goes through as normal. Help for the first alert still buzzes |
| D6 | Before the EMQX change (or with the rule removed) | "help topic refused by the broker", alerts confirmed as before |

Logger summary: Help received, ms after the confirm, timeouts, wrong help messages ignored.

## 6. Guesses, choices and things I could not do

**Part A answer: the Fob's time without NTP.** The Fob leaves `ts` out until NTP has set its clock. It never sends a wrong time: the ESP32 clock starts in the year 2000, and the Fob only uses it after 2023. Over WiFi this case never happens, because TLS needs the date (`clock_not_set`, then LoRa). So the risk is only LoRa alerts from a Fob that has had no WiFi since power on. Those cannot be age-checked, so the server keeps the old rule for them: accepted only if the counter is the highest seen. Under rule 4 they are never `stale`. But the problem you described is still there for them: a queued older alert that arrives after a newer one is turned away as `replay`. My suggested fix is GPS time (the wing sends UTC date and time in its RMC sentence). Options are in `docs/message-format.md`, "When the Fob has no clock". I did not change anything about it.

Choices I made without being told:
1. **No Security view exists.** Stale shows in Settings > Health > Rejected messages, which turns red for it, like replay and bad signature.
2. **Rule 4 applies to every unseen counter, also the newest.** So a WiFi alert the broker held for more than 15 minutes while the server was down is now `stale` (the LoRa copy usually got through first). Before, it was accepted.
3. **Drop order, generalised:** a higher type is never dropped for a lower one. So when the queue is full of SILENT and MEDICAL, a new STATUS or SUSPICIOUS is not queued (logged as `RETRY_GAVE_UP ... reason=queue_full`).
4. **Counter file missing** (brand new Fob) is `counter=new`, not a failure. A damaged file is a failure.
5. **Key check:** not the placeholder and exactly 32 hex characters (what `add_device.py` makes). A key typed in by hand with `--key` in another length would show red.
6. **GPS check:** at least one valid NMEA sentence within 5 s of start. A fix is not needed.
7. **The BOOT report** is not retried if it fails, and a button press stops it.
8. **Help LED:** a slow green blink along with the buzz (you only asked for the buzz). Remove it in `help_step()` if you do not want it.
9. **Help is sent only on Acknowledge**, not on Resolve of an alert nobody acknowledged. STATUS presses do not listen for help.
10. **No light during a retry,** and nothing on give up (the fail buzz already came at the press).
11. **Seen counters are kept 7 days.** An exact copy older than that is `stale`, not `duplicate`.
12. **The 2 s upkeep problem** was not written down anywhere, so I traced it in the code. `ntptime.settime()` (DNS plus a 1 s socket wait) and the hourly DNS refresh block the loop, and the button was only polled. Same cause as a retry blocking. Fixed with `presslog.py`: a tap during a block is now counted with its real time (tested on the laptop). The block itself still happens, so the press is handled up to about 2 s late, but it is no longer lost or miscounted. The DNS refresh now also waits if the button is in use.
13. `DUPLICATE_WINDOW_S` was removed from `server/config.py`, because the 10 minute window no longer exists.

Could not do or check:
- Nothing was run on the boards. The new firmware uses three things I could not test on the laptop:
  - a hard interrupt on the button pin (if MicroPython refuses `hard=True` on the C5, it falls back to a soft interrupt and prints "Button: soft interrupt")
  - `select.poll()` on the TLS socket for help messages
  - `machine.disable_irq()`
  
  The boot line "Button: interrupt" tells you which mode is running.
- I did not look at the dashboard in a browser, only built it and ran the contrast check.
- I could not check in the EMQX console that Serverless supports `${clientid}` in rules. If it does not, use one fixed rule per Fob.
- Motor and WiFi: the help listener sends MQTT pings, and the help message's QoS 1 reply, over WiFi. The ping waits while the motor runs. The QoS 1 reply goes out before the buzz starts.

## 7. Follow-up (server only)

### What changed

| File | Change |
|---|---|
| `server/validate.py` | The counter window replaces "must be the highest" and the stale rule. A counter never seen is accepted if it is no more than `COUNTER_WINDOW` (32) below the highest seen for that Fob, with or without `ts`. Already seen with a different message: `replay`. More than 32 below: `replay`. Age never rejects. New `age_tag()`: no tag, `late` (over 60 s) or `over_max` (over 15 minutes) |
| `server/config.py` | New `COUNTER_WINDOW` (32). `MAX_ALERT_AGE_S` (900) now only sets the "over 15 min" tag |
| `server/db.py` | `prune_seen()` never removes a counter inside the window, so a played-back copy inside the window is always caught as a `duplicate`. New `count_late()` for Health |
| `server/processor.py` | Returns `late`: none, `late` or `over_max` |
| `server/app.py` | Alerts have `late_over_max` |
| `server/stats.py` | `/api/stats` has `late_over_max` (the count in the range). CSV "Sent late" says "Yes, over 15 min, 1260 s" for those |
| `dashboard/src/components/Tags.jsx`, `styles/base.css` | Over 15 minutes: a yellow "Sent late (over 15 min)" tag with a warning icon. 60 s to 15 minutes: the gray "Sent late" tag, as before |
| `dashboard/src/components/SettingsModal.jsx` | New Health row "Sent late (over 15 min)", yellow with a warning icon when the count is 1 or more. Rejected messages: red for bad signature and replay (old "stale" rows still count as red) |
| `dashboard/src/mock/*.js` | One mock alert arrives 21 minutes late. The fake stale rejection is gone |
| `server/test_duplicates.py` | 58 checks. The counter window edges (exactly 32 below accepted, 33 below `replay`, with and without `ts`), a big jump up accepted, a 20 minute old alert accepted and tagged, pruning keeps the window. Checks that expected `stale` now expect acceptance with a tag. "Lower counter is replay" is now "lower unseen counter inside the window is accepted" |
| `server/test_attacks.py` | Still 19. The captured alert played back an hour later is now accepted and tagged over 15 min, not `stale` |
| `tests/test_help.py` | 51 checks. New: during a SILENT help message and 3 s after it, the LED is never set at all (no green) and the help buzz is never played |
| `docs/message-format.md`, `docs/dashboard.md`, `docs/how-to-run.md` | The new rule, the tags, the Health row, the test counts |

No firmware changed. Nothing new to copy to the Fob. Restart `app.py` and `serial_bridge.py`.

### SILENT and the green blink

In `firmware/fob/main.py`, `help_step()` only calls `self.led.show(GREEN, 400, 400, 2000)` and `self.motor.play("help")` when `helplisten.feedback(kind) == "help"`. `feedback()` in `firmware/lib/helplisten.py` returns None for SILENT. So a SILENT alert only logs "help for SILENT ctr N received: no buzz, no light". `tests/test_help.py` records every LED and motor call while a SILENT help message comes in, and for 3 s after. There are none.

### What the window costs

Someone who records a real alert that never reached the server (for example by jamming the Relay) can play it back later, as long as the Fob has sent fewer than 32 messages since. It is accepted. If it has `ts`, it shows "Sent late (over 15 min)" and the yellow Health warning. If the Fob's clock was not set, nothing marks it.

### Later firmware change: GPS time

Not built. The Fob should set its clock from GPS time when NTP has not run (no WiFi since power on):
- The GPS wing already sends the UTC date and time in its RMC sentence. `gps.py` reads only GGA today.
- With it, LoRa-only alerts get a `ts`, so "Sent late", the over 15 min warning, and the BOOT time work for them too.
- It could also let the Fob use TLS (WiFi) before NTP has run. That needs a check that the GPS time is valid, so a bad fix never sets a wrong date.
- Indoors with no fix since power on, there is still no time.

### Test results (laptop)

| Test | Result |
|---|---|
| `server/test_attacks.py` | 19 of 19 |
| `server/test_duplicates.py` | 58 of 58 |
| `tests/test_help.py` | 51 of 51 |
| `tests/test_selfcheck.py` | 39 of 39 |
| `npm.cmd run build` | builds |
| `npm.cmd run contrast` | all pairs pass |

## 8. Crash during HELP_LISTEN (2026-11-11, 15:15:00)

Log: `logs/2026-11-11/150725_features_boot/`. A press stopped the BOOT report, the SUSPICIOUS alert (ctr 238) was confirmed over WiFi, HELP_LISTEN started, and 5.8 s later: Guru Meditation Error, Cache error, MCAUSE 0x19, reboot.

### What I found

1. **`import select` every 10 ms.** `helplisten.socket_ready()` ran `import select` and made a new poller on every loop while listening. In MicroPython, `select` is an "extensible" built-in: a file with the same name on the file system wins, so each import looks on the file system first (`/select.py`, `/lib/select...`). That is a flash read every 10 ms, for 2 minutes, with WiFi busy. The crash dump at 0x4082b360 holds the text "/lib/select", which fits. A cache error means something ran from flash while the flash cache was off, and a flash read turns the cache off for a moment. I cannot prove from the dump which code that was, but this was the only thing touching flash over and over at that time. The first listen (ctr 236) ran 120 s without a crash, so it is a timing race, not a sure thing.
2. **Other imports inside functions** (each one a file system lookup when it runs): `ntptime` (every NTP retry), `sx127x` and `machine.SPI` (each time the radio is set up again, which can happen in the middle of a LoRa send), `machine.I2C`, `bme280`, `max17048`, `gps`, `machine.WDT`, `ssl`, `neopixel` and `machine` (once each at boot). All moved to the top of `main.py`. `helplisten.py` now imports `select` at the top and makes one poller per connection.
3. **Flash writes and reads near the network:**

| What | When | Now |
|---|---|---|
| Counter file write | before every send | Must stay before the send (a crash can never reuse a counter). The help listener is now closed first, so the TLS connection is gone before the write |
| `/queue.json` write | after a retry, after an unconfirmed send | After a retry that gets through, the Fob may be listening again. The save now waits until listening ends. A new unconfirmed alert is saved at once, but the listener is already closed then |
| CA file `os.stat` | every WiFi send | Checked once at boot, then remembered |
| CA file read | first WiFi send | Now at boot (`boot_wifi`) |
| `/counter.txt` read | boot self-check | Boot only |
| presslog | never | RAM only |

   During HELP_LISTEN nothing touches flash now. During a send, only the counter write, and it has to happen before the radio sends. `tests/test_imports.py` runs 2 minutes of HELP_LISTEN on the real `main.py` and counts every file system call: zero.

4. **The button interrupt.** In MicroPython 1.27 (`ports/esp32/machine_pin.c`) the pin interrupt has no hard mode. That is why the log says "Button: soft interrupt". The C handler is not in IRAM and the interrupt service is installed with flags 0, so ESP-IDF holds it back while flash is busy. The handler only queues our Python function (`mp_sched_schedule`), which then runs later in the normal loop. So the button handler cannot run while flash is busy, and it is not the likely cause. Our Python handler (`EdgeLog.irq`) only reads the clock and the pin into arrays, and the test checks that.

### Reset reason

The BOOT report now has `rst` = `machine.reset_cause()`. In MicroPython 1.27 a crash and `machine.reset()` both give 2. The Fob never calls `machine.reset()`, so 2 shows as "Restarted after a crash" (orange) on the Devices page and in the device panel. 1 is "Power on" (also the RST button and a battery dip). The SELF_CHECK line ends with `reset=crash fw=...`. A BOOT from older firmware (no `rst`) is still accepted and shows "Not reported". `FW_VERSION` is now `2026.11.11b`.

### Newer MicroPython

On micropython.org the Thing Plus ESP32-C5 page lists v1.28.0 (2026-04-06), v1.29.0 (2026-08-24, the latest release) and v1.30.0 previews up to 2026-11-06. The board runs v1.27.0 (2026-02-04).
- v1.28.0 notes: the Thing Plus ESP32-C5 board definition was added. No mention of cache errors.
- v1.29.0 notes: "use ESP-IDF abstraction for CPU cycle count (fix ESP32-C5)", and "note CONFIG_SPI_FLASH_ROM_IMPL may cause cache error / MMU fault". That second line is about a build setting, not a code fix, and I cannot tell if your v1.27.0 build uses it.
- Nothing was flashed.

### Files to copy to the Fob

| Laptop file | Board path |
|---|---|
| `firmware/fob/main.py` | `/main.py` |
| `firmware/lib/helplisten.py` | `/helplisten.py` |
| `firmware/lib/selfcheck.py` | `/selfcheck.py` |

The other Fob files are unchanged since section 3. Restart `app.py` and the bridge (the server now stores `rst`).

### Board test: try to make the crash happen again

Logger: `python tests\field_log.py --label crashhunt --relay COM14 --forward`. Server with MQTT on. After each step, look for "Guru Meditation" in the logger and for "after a crash" on the Devices page.

| # | Do | Expect |
|---|---|---|
| 1 to 5 | B5 five times: press RST, then press twice (SUSPICIOUS) during the red light, so the press stops the BOOT report. Wait 2.5 minutes each time (the whole HELP_LISTEN) | `BOOT report stopped by a button press`, the SUSPICIOUS confirmed over WiFi, `HELP_LISTEN`, then `HELP_TIMEOUT` after 2 minutes. No crash. Next boot `SELF_CHECK ... reset=power_on` |
| 6 to 10 | Five normal SUSPICIOUS presses, 2.5 minutes apart. Acknowledge two of them on the dashboard | Each: confirmed, `HELP_LISTEN`. The acknowledged ones: `HELP_RECEIVED` and three slow pulses. The others: `HELP_TIMEOUT`. No crash |
| any | If it crashes | The next `SELF_CHECK` says `reset=crash`, and the Devices page says "Restarted after a crash". Keep the raw log and send it to me |

To compare: on the old firmware today, 1 of 2 listens crashed (ctr 236 was fine, ctr 238 crashed). If the new firmware runs all 10 with no crash, that supports the cause above. It does not prove it.

### Test results (laptop)

| Test | Result |
|---|---|
| `tests/test_imports.py` (new) | 26 of 26 |
| `tests/test_selfcheck.py` | 45 of 45 |
| `tests/test_help.py` | 51 of 51 |
| `tests/test_retry_queue.py` | 71 of 71 |
| `tests/test_wifi_errors.py` | 58 of 58 |
| `tests/test_sendpath.py` | 37 of 37 |
| `server/test_attacks.py` | 19 of 19 |
| `server/test_duplicates.py` | 58 of 58 |
| `npm.cmd run build`, `npm.cmd run contrast` | builds, all pairs pass |

## 9. BOOT over LoRa gave bad_json (2026-11-11, selfcheck_b4)

The Relay's line for BOOT ctr 243 started with 64 bytes left over from an earlier print (`SAFEPING_MSG {"bat": 100, "type": "BOOT", "wifi": 0, "fail": 0, `), then the full message. 64 bytes is the size of the board's USB serial buffer, and that earlier message appears nowhere else in the logs. So it was most likely printed while no program had COM14 open, and the start of it stayed in the buffer. The Relay and the server were fine. `serial_bridge.handle_line()` parsed from the first `SAFEPING_MSG`, which gave bad_json.

Fix: `serial_bridge.message_text()` and `field_log.msg_text()` take the JSON after the LAST `SAFEPING_MSG` in the line, and say how many bytes were dropped. New test `server/test_serial_bridge.py` (11 checks) uses the real line from the log. The real line now reaches the signature check (the test does not have the real key), and the same message signed with a test key is saved as a boot report with link `lora`.

BOOT ctr 243 itself was not saved by the server. It is in the Relay's `queue.txt`.

`reset ?` in the logger summary: that run's Fob still had the old firmware (the log says `firmware 2026.11.11`, and the SELF_CHECK line has no `reset=`). With `2026.11.11b` on the Fob, the summary shows `reset power_on`, `reset crash` and so on. For older firmware it now says `reset not reported (firmware before 2026.11.11b)` instead of `?`.

LED patterns: `docs/led-patterns.md`. No LED behavior was changed.

Copy: nothing new to the Fob or the Relay for this fix. It is laptop and server code (`server/serial_bridge.py`, `tests/field_log.py`). The Fob still needs the section 8 files to report the reset reason.

## 10. Crash test results, LED colors, stopped BOOT reports (2026-11-11, crashtest)

Board run `logs/2026-11-11/153933_crashtest/`: no crash in 9 HELP_LISTENs, help received 3 of 3.

### "LoRa had a problem" on ctr 248, 250, 252, 254

The radio was fine. It was the logger. Each of those alerts was the last one before a reboot. The next boot printed "LoRa fallback on: CS 26 RST 6" and "LoRa acks: ...". The logger counted any Fob line starting with "LoRa" as a problem for the last alert. ctr 256 had no reboot after it, so it was not marked.

Fix (`tests/field_log.py`): a "SafePing Fob ..." boot line ends the last alert, and only real radio trouble counts ("LoRa failed", "LoRa check", "LoRa: setting the radio up again", "LoRa worked after"). `server/test_serial_bridge.py` replays the crashtest log: no alert is marked now.

Stopping the BOOT report never touches LoRa. The press stops it in the WiFi step, at "connect" (it shows as "WiFi send failed at connect: time budget used up"), before any LoRa send. In all 5 runs the press was already in the button log when the BOOT send started, so it stopped 6 ms in.

### Stopped BOOT reports are sent later

`main.py`: a press that stops the BOOT report keeps the signed message (`BOOT_STOPPED ctr=... reason=button`). When the Fob is idle again (the press handled, the motor quiet), `resend_boot()` sends the same message (`BOOT_RESEND ctr=...`). If the press was an alert confirmed over WiFi, the Fob is listening for help, and the BOOT report goes on that same connection (`helplisten.send_on_connection()`), so listening never stops. That connection is already subscribed to the ack topic. If it does not carry the BOOT report, the normal WiFi-then-LoRa send is used. The logger counts "stopped by a press, sent later" and "stopped by a press, not sent yet".

### bad_json at 15:44:45

The Relay line was 64 bytes left over from BOOT ctr 246 (`SAFEPING_MSG {"wifi": 1, "ctr": 246, "ts": 1794411525, "v": 1, `), then a plain Relay line ("ignored a packet that is not a SafePing alert"), not a message. Section 9's fix took the text after the last `SAFEPING_MSG`, which here was the cut-off piece.

Cause: the Relay prints while no program has COM14 open (between log runs), and the start of that line stays in the board's 64-byte USB buffer until the next print.

Fix (`server/serial_bridge.py`): the Relay prints `SAFEPING_MSG` only after its own JSON check passed. So a `SAFEPING_MSG` line that is not one whole JSON object is broken console output, never a radio message. The bridge (and `--forward`) now prints it locally and does not send it to the server, so it no longer shows up as bad_json in the rejected table. BOOT ctr 246 itself is only in the Relay's `queue.txt`.

Also seen in that line: ctr 246 has `ts` 1794411525, about 6 hours behind the boots around it. That BOOT was sent with WiFi off, so the clock was not set by NTP. Most likely Thonny had set the board's clock to local time (Central time is 6 hours behind UTC). Alerts sent with such a clock would show "Sent late (over 15 min)". Not changed. Thonny has a setting to use UTC for the device clock, and GPS time (section 7) would fix it too.

### LED colors

Each color now means one kind of thing. The full table is in `docs/led-patterns.md`. Red: MEDICAL only. Yellow: SUSPICIOUS only. White: STATUS sending only. Green: good news. Orange: a problem. Blue: starting up and joining WiFi. SILENT: nothing. Orange is now 255, 45, 0 (it looked yellow before). `tests/test_led.py` (30 checks) records every LED call and fails if a color is used for two kinds of things.

### Files to copy to the Fob

| Laptop file | Board path |
|---|---|
| `firmware/fob/main.py` | `/main.py` |
| `firmware/lib/helplisten.py` | `/helplisten.py` |

`FW_VERSION` is now `2026.11.11c`. Nothing for the Relay. Restart `serial_bridge.py` (or the logger with `--forward`).

### Test results (laptop)

| Test | Result |
|---|---|
| `tests/test_led.py` (new) | 30 of 30 |
| `tests/test_selfcheck.py` | 57 of 57 |
| `tests/test_imports.py` | 26 of 26 |
| `tests/test_help.py` | 51 of 51 |
| `tests/test_retry_queue.py` | 71 of 71 |
| `tests/test_sendpath.py` | 37 of 37 |
| `tests/test_wifi_errors.py` | 58 of 58 |
| `server/test_serial_bridge.py` | 17 of 17 |
| `server/test_attacks.py` | 19 of 19 |
| `server/test_duplicates.py` | 58 of 58 |

## 11. Crash when a press stopped a retry (2026-11-13, 12:31:31)

Log: `logs/2026-11-13/121605_retry/` (raw file, lines 527 to 700). Relay unplugged, fake WiFi, no clock. Four alerts queued (ctr 321 to 324). RETRY_TRY ctr=322, LoRa try 1, a press, `RETRY_STOPPED ctr=322 try=1 reason=button` at 12:31:30.829, then the crash. The press never got a counter and was not sent after the reboot.

### Two crashes, not one printed twice

The raw log has two different dumps with a full reboot between them (`ESP-ROM`, `rst:0xc (SW_CPU)`, `entry 0x4084bba0`):

| | First (12:31:31.268) | Second (12:31:34.857) |
|---|---|---|
| SP | 0x4082af60 | 0x4082b1e0 |
| S5, S6, S7 | 0x4, 0x20, 0x2003e0 | 0x1000, 0x80, 0x2004c0 |
| Stack text | none readable | `binascii.mpy` at 0x4082b5c0 |

The second one happened 3.5 s after the first reboot, before the `SafePing Fob` line. `import binascii` is the first line of code in `main.py`, so the Fob was looking up `binascii.mpy` on the file system. At that moment WiFi was not started, the LoRa radio was not set up, the button interrupt did not exist yet and nothing was being written. Only a file system read. The third boot worked (`reset=crash`).

### The same crash three times

The 2026-11-11 crash (section 8) and both of today's have the same fingerprint:

- Program counter in the chip's ROM (0x40000344 or 0x4002a37e, return address 0x4002a382 or 0x4002a390).
- The same registers A3 = 0x08088000, A4 = 0x600c8000, S3 = 0x421b1170, S8 = 0x421b10dc.
- The same firmware return addresses on the stack: 0x4204906a, 0x4204d018, 0x42188d64, 0x4206997c.

So it is one bug in one code path, the file system's flash access, reached from three callers: an import during HELP_LISTEN, the queue save after RETRY_STOPPED, and an import at boot. Our code can only lower how often it touches flash. It cannot remove the bug.

### Every flash access from RETRY_STOPPED to the new press's send

| When | What | Flash |
|---|---|---|
| Right after RETRY_STOPPED | `save_queue()`: write `queue.json.tmp` (about 1.3 KB for 4 entries), close, rename to `queue.json` | 2 writes (data, then file system metadata). The crash was almost certainly here |
| Then | Press handled: 600 ms tap window, then STATUS | none (RAM and pins only) |
| At the send | `next_counter()`: read `counter.txt`, write `counter.txt` | 1 read, 1 write |
| After an unconfirmed send | `queue_retry()`: the same save as above | 2 writes |
| Anywhere | All MicroPython code runs from flash through the cache | reads, all the time |

At the save, the ESP32's own radio was off. `deliver()` had already switched WiFi off (`wifi_quiet(for_lora=True)`) before LoRa, 4.5 s earlier. The SX1276 is a separate chip on SPI, and its G0 pin is not wired, so it cannot interrupt the ESP32. The button interrupt is a soft interrupt (section 8). So no radio work and no interrupt of ours was running at the same time as the save. The second crash had none of them at all. The 12:26:51 press during a retry ran the same code with no crash, so this happens by chance, not every time.

### Likely cause: the flash driver in ROM

MicroPython 1.28's board files for the SparkFun Thing Plus ESP32-C5 include `sdkconfig.free_ram`, which sets `CONFIG_SPI_FLASH_ROM_IMPL=y`. That runs the flash driver from the chip's ROM. MicroPython 1.29 added a warning to that file: it "may cause panics (Cache error / MMU entry fault error)" (PR 19469, found on an ESP32-S3). 1.29 no longer uses `free_ram` for any ESP32-C5 board. The program counter in ROM in all three dumps fits this. It is not proven: the ROM address is not a named function, and I do not have the `.elf` of the 1.27 build on the board. With that `.elf`, `riscv32-esp-elf-addr2line -e firmware.elf 0x4204906a 0x4204d018 0x42188d64 0x4206997c` would name the four functions (laptop only, no board).

### Fix: a press kept in RTC memory (`pressrec.py`)

The press is written to `machine.RTC().memory()` the moment the Fob sees it, before any flash access. RTC memory is RAM that keeps its content through a crash reset and a soft reset. In MicroPython 1.27 it uses `RTC_NOINIT_ATTR`, so the bootloader does not clear it. It is lost on power off. Writing it never touches flash.

| Stage | Written when | After a crash, at boot |
|---|---|---|
| `press` (taps so far) | first sign of a press while idle, every RETRY_STOPPED and BOOT_STOPPED, each release | sends the kind the taps give: 3 or more MEDICAL, 2 SUSPICIOUS, else STATUS |
| `kind` | the pattern is decided (STATUS and SILENT at once, SUSPICIOUS and MEDICAL at the start of the cancel window) | sends that kind with a new counter |
| `signed` | right after signing, before the send | the same signed message (same ctr and sig) goes into the retry queue, due at once |

It is cleared when the alert is confirmed, saved in `queue.json`, or cancelled, and when a bounce never becomes a press. New log lines: `PRESS_FOUND stage=... boots=N`, `PRESS_RESUMED ...`, `PRESS_DROPPED ... reason=crashed_too_often` (a record found on 3 boots in a row is dropped on the 4th, so it cannot make the Fob restart forever). The boot prints `Press record: RTC memory, kept through a crash`, or a WARNING if this firmware has no RTC memory, and then the Fob works as before.

Choice to check: a press cut off before its pattern ended (today's case, 440 ms into a tap) is sent as STATUS. If you want something else for an unknown pattern, say so.

`FW_VERSION` is now `2026.11.13a`.

### MicroPython 1.29: steps and risks

Not flashed. Steps when you decide to:

1. Run `tests/flash_stress.py` on 1.27 first (below), to get a "before" number.
2. In Thonny, download every file on the Fob to a laptop folder, including `config.py`, `counter.txt`, `queue.json` and `/certs`. Write down the number in `counter.txt`.
3. Download the SPARKFUN_THINGPLUS_ESP32C5 v1.29.0 `.bin` and its `.elf` from micropython.org. Keep the 1.27 `.bin` you flashed before, so you can go back.
4. Flash with Thonny's esptool installer, with "erase flash" on (the build settings changed, so start clean).
5. Copy every file back, `counter.txt` included. The counter must never go back, or the server rejects every message as a replay.
6. Run the self-check, then the board tests below, then `flash_stress.py` again.

Risks:

- `counter.txt` lost or older after the erase: the server rejects everything. Step 5 prevents it.
- 1.29 reworks the I2C driver (new driver on ESP-IDF 5.5.2). The BME280 and the battery gauge must be checked again (SELF_CHECK `battery=ok pressure=ok`).
- ESP-IDF moves from 5.5.1 to 5.5.2: WiFi, TLS and MQTT must be checked again (one confirmed alert over WiFi, one HELP_RECEIVED).
- The board's flash moves to QIO 80 MHz (`sdkconfig.flash_qio_80m`). If the board does not boot, flash 1.27 back.
- `machine.reset_cause()` numbers and the pin interrupt (soft or hard) may change. SELF_CHECK must still say `reset=power_on` after the RST button. The `Button:` line will show which interrupt mode it got.
- RTC memory must survive a crash on 1.29 too (test 2 below).
- It may not fix the crash. The cause above is likely, not proven. The stress test numbers decide.

### Board tests

| # | Do | Expect |
|---|---|---|
| 1 | Normal boot | `Press record: RTC memory, kept through a crash`. No `PRESS_FOUND` |
| 2 | In the Thonny Shell, after stopping main.py: `import pressrec, machine; pressrec.PressRecord(pressrec.RtcStore(machine)).kind("STATUS"); machine.reset()` | After the reboot: `PRESS_FOUND stage=kind boots=1`, `PRESS_RESUMED kind=STATUS stage=kind`, one STATUS sent, then the BOOT report |
| 3 | Same as 2, but end with `machine.mem32[0] = 1` instead of `machine.reset()`. That makes a real Guru Meditation crash | Same as 2, and `reset=crash` |
| 4 | Same as 2, then unplug the battery and USB for 10 s before it boots | No `PRESS_FOUND` (RTC memory does not survive a power cut) |
| 5 | Relay unplugged, press during a retry (like today) | `RETRY_STOPPED`, then the press is sent. Nothing new in the log if it does not crash |
| 6 | `tests/flash_stress.py` (Run current script, main.py stopped) | `STRESS_DONE cycles=3000`. A crash: keep the whole Shell text and the last `cycle` line |

### Not fixed, for the list

- Counter write is not crash-safe. `next_counter()` writes `counter.txt` in place. A crash in that write can leave it empty. With no clock, the Fob then restarts the counter from 0, and the server rejects every message as a replay. The queue already uses the safe way (write a .tmp file, then rename). This is the most important item here.
- BOOT reports that fail are not retried. They are not queued, by design (section 3). A stopped one is resent once.
- With no clock, a late alert cannot be marked "Sent late". It has no `ts`. The Fob knows the age (`age_s`), but sending it needs a new field in `docs/message-format.md` first.
- The SMS shows the arrival time, not the press time (`server/notify.py` `format_alert()` uses `received_at`). Using `ts` is small when there is a clock. With no clock there is no press time, so it is tied to the item above.

### Files to copy to the Fob

| Laptop file | Board path |
|---|---|
| `firmware/fob/main.py` | `/main.py` |
| `firmware/lib/pressrec.py` | `/pressrec.py` (new) |
| `tests/flash_stress.py` | do not copy. Open it in Thonny and use Run current script |

Nothing for the Relay or the server.

### Test results (laptop)

| Test | Result |
|---|---|
| `tests/test_press_record.py` (new) | 34 of 34 |
| `tests/test_imports.py` | 27 of 27 (now also checks `pressrec.py`) |
| `tests/test_retry_queue.py` | 71 of 71 |
| `tests/test_help.py` | 51 of 51 |
| `tests/test_selfcheck.py` | 57 of 57 |
| `tests/test_sendpath.py` | 37 of 37 |
| `tests/test_wifi_errors.py` | 58 of 58 |
| `tests/test_led.py` | 30 of 30 |

## 12. "Press cut off by a restart", crash-safe counter (2026-11-14)

Edwin's two decisions on section 11. `docs/message-format.md` was changed first.

### A press cut off by a restart

After a restart, an unfinished pattern is sent as the type its recorded presses give: 3 or more = MEDICAL, 2 = SUSPICIOUS, a hold that started = SILENT, 1 = STATUS. These rules are checked in that order.

- **Press still down:** a press that is still down counts as one more press. If it has been down for `CUT_HOLD_MS` (1 s, new setting), it is a hold that started instead. Today's 12:31:30 press (down about 0.4 s) is therefore STATUS.
- **Already decided:** a press whose type was already decided (STATUS, SILENT, or SUSPICIOUS and MEDICAL in the cancel window) is sent as that type.
- **The flag:** both of these are sent with a new counter and the new field `"cut": 1`.
- **Signed:** a press that was already signed goes out as the same message from the queue, with no `cut`, because its signature cannot change.

What the record holds now (`pressrec.py`): the press stage, the taps so far, whether the button is down, and whether a hold started. `main.py` writes it when the button goes down, comes up, and passes `CUT_HOLD_MS`.

| Where | Change |
|---|---|
| `docs/message-format.md` | New field `cut` (alerts only, value `1`). Signed at the end (`... \| bat \| cut`) only when present, so every other message signs as before. New section "Press cut off by a restart". Size note: about 251 bytes for the largest alert with `cut`, 255 at the absolute worst case (a 10-digit counter) |
| `server/validate.py` | Signing string with `cut`. `cut` must be `1` and only on an alert type, otherwise `bad_format` |
| `server/db.py` | New column `alerts.cut_off` (added on start, old rows get 0) |
| `server/processor.py`, `server/app.py` | Stores it. The API gives `cut_off` true or false on every alert |
| Dashboard | Gray tag "Press cut off by a restart" (power icon) next to the time on Live and in the device panel's history, and in the alert panel header. The list layout of the panel has a row that explains it. Mock mode shows it on one SUSPICIOUS alert |

Not added yet: a column in the CSV and Excel exports.

### Crash-safe counter

- **Write (`counterfile.py`, new):** `counter.txt.tmp` is written in full, then renamed over `counter.txt`, so the file is always the old or the new value. Reading takes the higher of the two files that read as a whole number.
- **RTC copy:** every new counter goes into RTC memory before the flash write (`pressrec.py`, field `ctr`).
- **Boot jump:** on every boot, after the queue is read and before the first send, the counter jumps `COUNTER_BOOT_JUMP` (8, new setting) ahead of the highest of: the file, the RTC copy, a signed press in RTC memory, and every counter in the queue. Log line: `COUNTER_JUMP from=... to=... rtc=... queue=...`.
- **Damaged file:** with no clock, a damaged counter file now continues from the RTC copy instead of 0.
- **Self-check:** reads through the same code, so a valid `.tmp` next to a damaged `counter.txt` is not a failure.

A cost to know: the server's counter window is 32. Each boot uses 9 numbers (the jump of 8, then 1 for the BOOT report). If the Fob restarts 4 times while an alert waits in the queue (10 minutes), that alert falls below the window and the server rejects it as `replay`. It is written in `message-format.md`. If that is a problem, the choices are a smaller jump or a bigger `COUNTER_WINDOW` on the server.

`FW_VERSION` is now `2026.11.14a`.

### Board tests

| # | Do | Expect |
|---|---|---|
| 1 | Normal boot | `COUNTER_JUMP from=N to=N+8`, then the BOOT report with counter N+9 |
| 2 | Section 11 test 2 (`.kind("STATUS")`, then `machine.reset()`) | `PRESS_RESUMED kind=STATUS stage=kind ... cut=1`. On the dashboard, the STATUS shows "Press cut off by a restart" (turn on "show STATUS" on Live) |
| 3 | In the Thonny Shell, after stopping main.py: `import pressrec, machine; r = pressrec.PressRecord(pressrec.RtcStore(machine)); r.load(); r.pressing(1); r.hold(); machine.mem32[0] = 1` | A real crash. After it: `PRESS_RESUMED kind=SILENT stage=press taps=1 down=1 hold=1 ... cut=1`, `reset=crash` |
| 4 | Same as 3 with `r.tap(2)` instead of `r.pressing(1); r.hold()` | `PRESS_RESUMED kind=SUSPICIOUS ... cut=1`, and a text to the duty phone. The text does not mention the restart (not asked for) |
| 5 | Reboot 3 times in a row with the RST button | Each boot jumps by 8. The server accepts each BOOT report |

### Files to copy

**Fob (Thonny):**

| Laptop file | Board path |
|---|---|
| `firmware/fob/main.py` | `/main.py` |
| `firmware/lib/pressrec.py` | `/pressrec.py` |
| `firmware/lib/counterfile.py` | `/counterfile.py` (new) |

Leave `counter.txt` on the board as it is. The first boot jumps it by 8.

**Server:** `server/validate.py`, `server/db.py`, `server/processor.py`, `server/app.py` changed in place. Restart `app.py`, the MQTT listener and `serial_bridge.py`. The new column is added on start. The dashboard was rebuilt (`npm.cmd run build`), and Flask serves the new `dashboard/dist`.

Nothing for the Relay.

### Test results (laptop)

| Test | Result |
|---|---|
| `tests/test_press_record.py` | 55 of 55 (cut rule, 6 cut-off patterns through the real button code, the server side) |
| `tests/test_counter.py` (new) | 22 of 22 (a crash at 4 points of the counter write, the boot jump) |
| `tests/test_imports.py` | 28 of 28 (now also checks `counterfile.py`) |
| `tests/test_retry_queue.py` | 71 of 71 |
| `tests/test_help.py` | 51 of 51 |
| `tests/test_selfcheck.py` | 57 of 57 |
| `tests/test_sendpath.py` | 37 of 37 |
| `tests/test_wifi_errors.py` | 58 of 58 |
| `tests/test_led.py` | 30 of 30 |
| `server/test_attacks.py` | 19 of 19 |
| `server/test_duplicates.py` | 58 of 58 |
| `server/test_serial_bridge.py` | 17 of 17 |
| `npm.cmd run build`, `npm.cmd run contrast` | builds, all pairs pass |
