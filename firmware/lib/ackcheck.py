"""Signed acks for SafePing LoRa. Used by the Fob and the Relay (and later the server).

Why: an unsigned "ACK" could be faked by anyone with a LoRa radio, and the Fob would
tell the wearer "help has it" when it does not. Signed acks stop that.

ack key  = HMAC-SHA256(device secret key, "safeping-ack-v1")
           The Relay holds only ack keys, never the device secret. So a stolen Relay
           could fake acks for its Fobs, but could never fake alerts.
ack text = "ACK <id> <ctr> <mac>"
           mac = first 16 hex characters of
                 HMAC-SHA256(ack key, "ACK|<id>|<ctr>|<the alert's sig>")
           Tied to that exact alert, so an old ack cannot be replayed for a new alert,
           and nobody without the ack key can make one.

The server can make the same ack later (it knows every device secret), so moving the
ack from the Relay to the server will not change the format.
"""
import binascii
import hashlib

LABEL = b"safeping-ack-v1"
MAC_HEX = 16                 # 64 bits of the HMAC, plenty for a one-time ack, keeps the packet small


def hmac_sha256(key, message):
    """HMAC-SHA256. MicroPython has no hmac module, so it is written out here."""
    block = 64
    if len(key) > block:
        key = hashlib.sha256(key).digest()
    key = key + b"\x00" * (block - len(key))
    inner = hashlib.sha256(bytes(b ^ 0x36 for b in key) + message).digest()
    return hashlib.sha256(bytes(b ^ 0x5C for b in key) + inner).digest()


def ack_key(secret_key):
    """secret_key as bytes. Returns the 32 byte ack key."""
    return hmac_sha256(secret_key, LABEL)


def ack_key_hex(secret_text):
    """For setting up the Relay: the ack key as 64 hex characters."""
    return binascii.hexlify(ack_key(secret_text.encode())).decode()


def ack_text(key, device_id, ctr, sig):
    """The exact ack the Relay sends and the Fob expects. key is the ack key (bytes)."""
    body = "ACK|{}|{}|{}".format(device_id, ctr, sig).encode()
    mac = binascii.hexlify(hmac_sha256(key, body)).decode()[:MAC_HEX]
    return "ACK {} {} {}".format(device_id, ctr, mac)


# ---------- "help is coming" (message-format.md) ----------
# Sent by the SERVER when staff press Acknowledge. The Relay never makes one.
# help key  = HMAC-SHA256(device secret key, "safeping-help-v1")
# help text = "HELP <id> <ctr> <mac>", mac = first 16 hex characters of
#             HMAC-SHA256(help key, "HELP|<id>|<ctr>")
HELP_LABEL = b"safeping-help-v1"


def help_key(secret_key):
    """secret_key as bytes. Returns the 32 byte help key."""
    return hmac_sha256(secret_key, HELP_LABEL)


def help_text(key, device_id, ctr):
    body = "HELP|{}|{}".format(device_id, ctr).encode()
    mac = binascii.hexlify(hmac_sha256(key, body)).decode()[:MAC_HEX]
    return "HELP {} {} {}".format(device_id, ctr, mac)


def check_help(key, device_id, text, waiting):
    """Check a help message the Fob received. waiting is the ctrs it is listening for.
    Returns (ctr, None) when it is valid for one of them, else (ctr or None, reason):
      "not_help"      not a HELP line at all (unsigned or junk)
      "other_device"  for another Fob
      "other_ctr"     signed format, but not for an alert this Fob is waiting on
      "bad_signature" for a waiting ctr, but the mac is wrong"""
    if isinstance(text, (bytes, bytearray)):
        try:
            text = bytes(text).decode()
        except Exception:
            return None, "not_help"
    parts = text.strip().split(" ")
    if len(parts) != 4 or parts[0] != "HELP" or len(parts[3]) != MAC_HEX:
        return None, "not_help"
    if parts[1] != device_id:
        return None, "other_device"
    try:
        ctr = int(parts[2])
    except ValueError:
        return None, "not_help"
    if ctr not in waiting:
        return ctr, "other_ctr"
    if text.strip() != help_text(key, device_id, ctr):
        return ctr, "bad_signature"
    return ctr, None
