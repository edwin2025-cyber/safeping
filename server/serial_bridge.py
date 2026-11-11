"""Serial bridge: Relay (USB) -> server, no network needed.

The Relay prints every NEW SafePing alert it hears over LoRa as one line:
    SAFEPING_MSG {"v": 1, "id": "FOB-001", ...}
This script reads those lines from the Relay's USB port and hands each one to
processor.process(), the same code the MQTT listener uses. So the signature check,
the replay check, the database and the dashboard are exactly the same as over WiFi.

Why: the laptop cannot accept incoming connections (no admin to open the firewall),
but it can always read its own USB port.

Run it (from safeping-1/server, with Thonny CLOSED so COM14 is free):
    python serial_bridge.py --port COM14
Ctrl+C to stop. Run app.py in another window for the dashboard.
"""
import argparse
import json
import time

import db
import processor

try:
    import serial  # pyserial
except ImportError:
    serial = None

PREFIX = "SAFEPING_MSG "


def message_text(line):
    """The JSON after the LAST "SAFEPING_MSG " in a line, or None if there is none.

    Why the last one: on 2026-11-11 (logs/2026-11-11/152822_selfcheck_b4) the Relay's
    line started with 64 bytes left over from an earlier print, made while no program
    had COM14 open ('SAFEPING_MSG {"bat": 100, "type": "BOOT", "wifi": 0, "fail": 0, ').
    64 bytes is the size of the board's USB serial buffer. The real message came right
    after it on the same line, and parsing from the first prefix gave bad_json."""
    line = line.strip()
    at = line.rfind(PREFIX)
    if at < 0:
        return None
    if at > 0:
        print("[bridge] dropped {} bytes left over before the message: {}".format(at, line[:at][:80]))
    return line[at + len(PREFIX):]


def whole_message(text):
    """True if text is one complete JSON object. The Relay prints SAFEPING_MSG only after
    its own json.loads() worked, so a line that is not whole JSON is broken console output
    (left-over bytes from a print made while no program had the port open), never a radio
    message. On 2026-11-11 15:44:45 (crashtest) such a line was 64 left-over bytes of BOOT
    ctr 246 followed by "ignored a packet that is not a SafePing alert"."""
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False


def handle_line(line):
    """Returns the processor result for a SAFEPING_MSG line, or None for any other line.
    A SAFEPING_MSG line that is not a whole message is not sent to the server (it would
    be logged there as bad_json). It is printed here instead."""
    text = message_text(line)
    if text is None:
        return None
    if not whole_message(text):
        print("[bridge] not a whole message, broken Relay output, not sent to the server: {}".format(
            line.strip()[:120]))
        return None
    return processor.process(text, source="lora")


def open_port(port):
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = 0.2
    ser.dtr = False          # do not reset the Relay when the port opens
    ser.rts = False
    ser.open()
    return ser


def main():
    parser = argparse.ArgumentParser(description="Relay USB to SafePing server")
    parser.add_argument("--port", default="COM14")
    parser.add_argument("--echo", action="store_true", help="also print every other Relay line")
    args = parser.parse_args()
    if serial is None:
        raise SystemExit("pyserial is not installed. Run: python -m pip install pyserial")

    db.init_db()
    print("[bridge] reading {} (Ctrl+C to stop)".format(args.port))
    buf = b""
    ser = None
    while True:
        try:
            if ser is None:
                ser = open_port(args.port)
                print("[bridge] connected to {}".format(args.port))
            buf += ser.read(ser.in_waiting or 1)
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                text = raw.decode("utf-8", errors="replace").strip()
                try:
                    result = handle_line(text)
                except Exception as err:          # one bad line must never stop the bridge
                    print("[bridge] error: {}".format(err))
                    continue
                stamp = time.strftime("%H:%M:%S")
                if result is not None:
                    print("[bridge] {} {}".format(stamp, result))
                elif args.echo and text:
                    print("[relay]  {} {}".format(stamp, text))
        except KeyboardInterrupt:
            print("[bridge] stopped")
            break
        except Exception as err:                  # unplugged, port busy
            print("[bridge] {} problem: {}. Retrying in 2 s".format(args.port, err))
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            ser = None
            time.sleep(2)


if __name__ == "__main__":
    main()
