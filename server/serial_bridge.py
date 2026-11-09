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
import time

import db
import processor

try:
    import serial  # pyserial
except ImportError:
    serial = None

PREFIX = "SAFEPING_MSG "


def handle_line(line):
    """Returns the processor result for a SAFEPING_MSG line, or None for any other line."""
    line = line.strip()
    if not line.startswith(PREFIX):
        return None
    return processor.process(line[len(PREFIX):], source="lora")


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
