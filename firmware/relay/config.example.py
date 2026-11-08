# Relay settings. Copy this to the Relay as config.py (Thonny, Save as, MicroPython device)
# and fill in the real values there. The real config.py never goes in git.
#
# One ack key per Fob. Make it on that Fob in Thonny:
#     import ackcheck, config
#     ackcheck.ack_key_hex(config.SECRET_KEY)
# It prints 64 hex characters. The Relay never holds the Fob's real secret key.
# Redo this whenever a Fob gets a new SECRET_KEY.

ACK_KEYS = {
    "FOB-001": "paste-the-64-characters-from-ack_key_hex",
}
