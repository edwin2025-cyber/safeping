"""Feeds messages from the Fob's serial console to the real server code.

Use it when the Fob runs in Wokwi and the server runs on your laptop, since Wokwi
cannot reach your laptop's broker. Copy the console text from Wokwi into a file,
then run:

  python replay_serial.py serial.txt        (or:  python replay_serial.py < serial.txt)

It picks out the lines that start with SAFEPING_MSG and runs each one through the
same checks as a live message (signature, counter, device). The Fob must be
registered first, with the same key as its config.py:

  python add_device.py FOB-001 "Student Name" --key <SECRET_KEY from config.py>

The counter rule still applies. Feed the same line twice and the second one is
rejected as a replay, which is the correct behavior."""
import re
import sys

import db
import processor

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
MARK = "SAFEPING_MSG "


def main():
    source = open(sys.argv[1], encoding="utf-8", errors="replace") if len(sys.argv) > 1 else sys.stdin
    db.init_db()
    found = 0
    for line in source:
        line = ANSI.sub("", line).strip()
        if MARK not in line:
            continue
        payload = line.split(MARK, 1)[1]
        found += 1
        result = processor.process(payload)
        status = "accepted" if result["ok"] else "REJECTED ({})".format(result["reason"])
        print("{}: {}  {}".format(found, status, payload[:90]))
    if not found:
        print("No SAFEPING_MSG lines found.")


if __name__ == "__main__":
    main()
