"""The Fob's boot self-check: what is checked, the SELF_CHECK log line and the BOOT
message (message-format.md, "Boot report"). Pure logic, no pins, so
tests/test_selfcheck.py runs it on the laptop.

Required checks, with their bit in the BOOT message's "fail" field:
  key       1   SECRET_KEY is set and the right length
  counter   2   the counter file reads (a missing file on a brand new Fob is "new", not a failure)
  lora      4   the LoRa radio answers (version register 0x12)
  gps       8   the GPS wing sends data within a few seconds
  battery  16   the battery gauge reads
  pressure 32   the pressure sensor reads
Not required: wifi. No WiFi is not a failure, because LoRa still works.
"""

REQUIRED = (("key", 1), ("counter", 2), ("lora", 4), ("gps", 8), ("battery", 16), ("pressure", 32))
PLACEHOLDER_PREFIX = "paste-the-key"

# machine.reset_cause() on the ESP32 port (MicroPython 1.27, ports/esp32/modmachine.c):
#   1 PWRON_RESET      power on, the RST button, or a brownout (battery dip)
#   2 HARD_RESET       a crash (ESP_RST_PANIC) or a software restart (ESP_RST_SW,
#                      machine.reset()). The Fob never calls machine.reset(), so here it
#                      means a crash, like the cache error on 2026-11-11
#   3 WDT_RESET        a watchdog
#   4 DEEPSLEEP_RESET  woke from deep sleep
#   5 SOFT_RESET       MicroPython soft reset (Ctrl+D or Thonny)
#   0                  unknown
RESET_NAMES = {1: "power_on", 2: "crash", 3: "watchdog", 4: "deep_sleep", 5: "soft_reset"}


def reset_name(code):
    """Short word for the SELF_CHECK line."""
    return RESET_NAMES.get(code, "unknown")


def key_ok(key, length=32):
    """add_device.py makes 32 hex characters."""
    if not isinstance(key, str) or key.startswith(PLACEHOLDER_PREFIX) or len(key) != length:
        return False
    for ch in key.lower():
        if ch not in "0123456789abcdef":
            return False
    return True


def counter_state(text):
    """"ok" if the counter file text is a whole number, "new" if there is no file
    (text is None), "fail" if it is damaged."""
    if text is None:
        return "new"
    try:
        int(text.strip())
        return "ok"
    except ValueError:
        return "fail"


def fail_mask(results):
    """results maps a check name to "ok", "new", "off" or "fail". Returns the BOOT "fail" bits."""
    mask = 0
    for name, bit in REQUIRED:
        if results.get(name) == "fail":
            mask |= bit
    return mask


def summary_line(results, fw, reset=None):
    parts = ["SELF_CHECK"]
    for name, _ in REQUIRED:
        parts.append("{}={}".format(name, results.get(name, "fail")))
    parts.append("wifi={}".format(results.get("wifi", "fail")))
    if reset is not None:
        parts.append("reset={}".format(reset_name(reset)))
    parts.append("fw={}".format(fw))
    return " ".join(parts)


def parse_line(line):
    """The fields of a SELF_CHECK line as a dict, or None. Used by tests/field_log.py."""
    if not line.startswith("SELF_CHECK "):
        return None
    out = {}
    for part in line.split()[1:]:
        if "=" in part:
            name, value = part.split("=", 1)
            out[name] = value
    return out


def boot_message(device_id, ctr, ts, bat, mask, wifi_ok, fw, reset=None):
    """The BOOT message before it is signed. Fields left out when they have no value.
    reset is machine.reset_cause() (0 when it could not be read)."""
    msg = {"v": 1, "id": device_id, "type": "BOOT", "ctr": ctr}
    if ts is not None:
        msg["ts"] = ts
    if bat is not None:
        msg["bat"] = int(bat)
    msg["fail"] = mask
    msg["wifi"] = 1 if wifi_ok else 0
    msg["fw"] = fw
    msg["rst"] = 0 if reset is None else int(reset)
    return msg
