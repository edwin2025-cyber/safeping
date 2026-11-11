# Fob LED patterns

Every color and pattern the Fob's LED shows, what it means, and where it is in the code. This is the firmware as of `FW_VERSION = "2026.11.11c"` (`firmware/fob/main.py`). `tests/test_led.py` records every LED call on the laptop and checks the rule below.

The LED is one NeoPixel on IO27 (`LED_TYPE = "neopixel"`). All calls go through the `Led` class in `main.py` (`show(color, on_ms, off_ms, duration_ms)`, `off()`). `on_ms` and `off_ms` = 0 means steady. `duration_ms` = 0 means until something else changes it.

## The rule: one kind of meaning per color

| Color | RGB | Means | Used for |
|---|---|---|---|
| Red | 255, 0, 0 | MEDICAL, only | MEDICAL cancel window, MEDICAL sending |
| Yellow | 255, 180, 0 | SUSPICIOUS, only | SUSPICIOUS cancel window, SUSPICIOUS sending |
| White | 255, 255, 255 | STATUS, only | STATUS sending (dim) |
| Green | 0, 255, 0 | Good news | self-check passed, confirmed (every type), cancelled, help is coming |
| Orange | 255, 45, 0 | A problem | not confirmed (every type), self-check failed |
| Blue | 0, 0, 255 | The Fob busy with itself | starting up, joining WiFi |
| Nothing | | SILENT, always | SILENT never lights, not even "confirmed" or "help is coming" |

Orange changed from 255, 90, 0 to 255, 45, 0, because the old orange looked yellow on the NeoPixel (the "yellow blinks" at startup). Check on the board that it now looks clearly different from yellow. If it does not, lower the middle number further.

Low battery: under `LOW_BATTERY_PCT` (20%) every color is shown at 40% brightness (`Led.scale`, set in `refresh_battery()`). The startup lights come before the first battery read, so they are always full brightness.

## The final table

| When | Color and pattern | How long | Meaning | Code |
|---|---|---|---|---|
| Power on or RST | Steady blue | about 0.25 s (until WiFi starts) | Starting up | `boot()`: `BLUE, duration_ms=200` |
| WiFi joining at startup (then NTP and DNS) | Blue blink, 300 ms on, 300 ms off | up to `WIFI_BOOT_MS` (8 s), about 3.4 s on the bench | Joining WiFi | `boot_wifi()`: `BLUE, 300, 300` |
| WiFi off (`WIFI_SSID = "none"`) | no blue blink | | | `boot()` |
| Self-check running | Off | up to 5 s, usually a moment | | `boot()`: `led.off()` |
| Self-check passed | Steady green | 1 s | Good news | `show_check()`: `GREEN, CHECK_OK_MS` |
| Self-check failed | Steady orange | 3 s | A problem (the SELF_CHECK line and the Devices page say which part) | `show_check()`: `ORANGE, CHECK_FAIL_MS` |
| BOOT report, also when sent later | Off | | | `send_boot_report()`, `resend_boot()` |
| Ready, idle | Off | | | main loop |
| 2 presses (SUSPICIOUS cancel window) | Yellow blink, 500 ms on, 500 ms off | 2 s | SUSPICIOUS coming, tap to cancel | `start_pending()`: `YELLOW, 500, 500` |
| 3 or more presses (MEDICAL cancel window) | Red blink, 150 ms on, 150 ms off | 2 s | MEDICAL coming, tap to cancel | `start_pending()`: `RED, 150, 150` |
| Tap in the cancel window | Green blink, 150 ms on, 150 ms off (2 blinks) | 0.6 s | Cancelled, nothing sent | `cancel_pending()`: `GREEN, 150, 150, 600` |
| STATUS sending | Dim white, steady | while sending | Sending a status check | `show_sending()`: 15% white |
| SUSPICIOUS sending | Dim yellow, steady | while sending | Sending | `show_sending()`: 15% yellow |
| MEDICAL sending | Dim red, steady | while sending | Sending | `show_sending()`: 15% red |
| STATUS confirmed | Green, one 150 ms blink | 0.3 s | Good news | `show_result()`: `GREEN, 150, 150, 300` |
| SUSPICIOUS or MEDICAL confirmed | Steady green | 3 s (`CONFIRM_MS`) | Good news | `show_result()`: `GREEN, CONFIRM_MS` |
| Any type not confirmed | Steady orange | 3 s | A problem: not confirmed (it goes in the retry queue) | `show_result()`: `ORANGE, CONFIRM_MS` |
| Retry gets through (`RETRY_DONE`) | Same as confirmed: green | | Good news | `run_retries()` calls `show_result(kind, True)` |
| Retry tries, fails again, gives up, stopped | Off | | | `run_retries()` |
| Help is coming (SUSPICIOUS, MEDICAL) | Green blink, 400 ms on, 400 ms off, 3 blinks, with the three slow pulses | 2 s | Good news: a person saw it | `help_step()`: `GREEN, 400, 400, 2000` |
| SILENT, anything | Nothing | | | `fire_now()`, `show_sending()`, `show_result()`, `help_step()` |

## What changed on 2026-11-11 (firmware 2026.11.11c)

| Was | Now |
|---|---|
| Startup: steady white | Steady blue |
| Joining WiFi: orange blink (looked yellow) | Blue blink |
| Self-check failed: steady red | Steady orange |
| SUSPICIOUS confirmed: steady yellow | Steady green |
| MEDICAL confirmed: steady red | Steady green |
| STATUS confirmed: one white blink | One green blink |
| Retry got through: the type color | Green |
| Orange 255, 90, 0 | Orange 255, 45, 0 |

The buzz patterns are unchanged.

## Notes

1. The startup blue is set to 200 ms but lasts until the WiFi blink starts, because the LED is not updated during the 250 ms pause after it.
2. Blinks freeze for a moment during blocking calls (NTP, DNS, a TLS handshake), because the LED is only updated in the main loop.
3. Green now covers four kinds of good news. They differ by pattern: 1 s steady (self-check), 3 s steady (confirmed), fast double blink (cancelled), slow triple blink with pulses (help).
4. Orange covers two problems with the same pattern (steady). The self-check one is 3 s right after the blue startup lights. The "not confirmed" one comes right after a press and a dim sending light.
