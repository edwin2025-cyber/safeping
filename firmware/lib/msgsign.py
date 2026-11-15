"""The signing string and signature of every SafePing message (message-format.md,
"Signing"). Shared by the Fob and the Reference board, so both sign the same way.

The server builds the same string in server/validate.py. tests/test_ref.py and
tests/test_survey.py check that the two agree.

  signing_string(msg)   the fields joined by "|", in the order for this type
  sign(key_text, msg)   HMAC-SHA256 of the signing string, 64 lowercase hex

Pure code: no pins, no files, no network.
"""
import binascii
import ackcheck                      # hmac_sha256 (MicroPython has no hmac module)

SIGNED_FIELDS = ("v", "id", "type", "ctr", "ts", "lat", "lon", "acc", "p", "t", "bat")
BOOT_FIELDS = ("fail", "wifi", "fw", "rst")      # BOOT only, after the others
SENSOR_FIELDS = ("sensor",)                      # the Reference board's BOOT: "BME280@0x77"
CUT_FIELDS = ("cut",)                            # an alert that has "cut"
REF_FIELDS = ("pd", "n", "fw")                   # a REF that has "pd" (firmware/ref)
SURVEY_FIELDS = ("pd", "n", "fix", "sats", "aps")   # SURVEY only


def fields_for(msg):
    kind = msg.get("type")
    if kind == "BOOT":
        if msg.get("sensor") is not None:
            return SIGNED_FIELDS + BOOT_FIELDS + SENSOR_FIELDS
        return SIGNED_FIELDS + BOOT_FIELDS
    if kind == "REF":
        return SIGNED_FIELDS + REF_FIELDS if msg.get("pd") is not None else SIGNED_FIELDS
    if kind == "SURVEY":
        return SIGNED_FIELDS + SURVEY_FIELDS
    if msg.get("cut") is not None:
        return SIGNED_FIELDS + CUT_FIELDS
    return SIGNED_FIELDS


def aps_text(aps):
    """[[bssid, rssi, ch, ssid_hex], ...] as "bssid,rssi,ch,ssid;...". Every part is hex
    or a whole number, so a separator can never come from inside a value."""
    return ";".join(",".join(str(x) for x in ap) for ap in aps)


def signing_string(msg):
    parts = []
    for name in fields_for(msg):
        value = msg.get(name)
        if value is None:
            parts.append("")
        elif name == "aps":
            parts.append(aps_text(value))
        else:
            parts.append(str(value))
    return "|".join(parts)


def sign(secret_key, msg):
    """secret_key as text (the 32 hex characters from add_device.py)."""
    digest = ackcheck.hmac_sha256(secret_key.encode(), signing_string(msg).encode())
    return binascii.hexlify(digest).decode()
