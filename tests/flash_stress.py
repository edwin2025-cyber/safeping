# flash_stress.py - run on the Fob in Thonny (Run current script). Stop with Ctrl+C.
#
# Why: three cache-error crashes (2026-11-11 15:15:00, 2026-11-13 12:31:31 and
# 12:31:34) all crashed in the same place: inside a file system call. The third one
# happened at boot, in the first import of main.py, with no WiFi, no LoRa and no button
# interrupt running. This script does only file system work, the way the Fob does it,
# so the crash rate can be counted on MicroPython 1.27 and then on 1.29.
#
# Each cycle: write a file the size of a 4-entry queue.json, rename it (like
# retryq.save), read it back, and look up two files that do not exist (like an import).
# It never touches counter.txt, queue.json, config.py or anything in /certs.
# It writes only stress.tmp and stress.json, and removes them at the end.
#
# If the board crashes, Thonny shows the Guru Meditation dump. Save the whole Shell
# text. The last "cycle" line says how far it got.

import json
import os
import time

CYCLES = 3000            # about 2 to 5 minutes, depending on the flash
TEXT = json.dumps({"v": 1, "entries": [{"payload": "x" * 250, "sig": "0" * 64}] * 4})

print("flash stress: {} cycles, {} bytes per write".format(CYCLES, len(TEXT)))
start = time.ticks_ms()
done = 0
try:
    for i in range(CYCLES):
        with open("stress.tmp", "w") as f:
            f.write(TEXT)
        os.rename("stress.tmp", "stress.json")
        with open("stress.json") as f:
            if len(f.read()) != len(TEXT):
                print("READ BACK WRONG at cycle", i)
        for name in ("binascii.mpy", "lib/select.py"):
            try:
                os.stat(name)
            except OSError:
                pass
        done = i + 1
        if done % 100 == 0:
            print("cycle", done, "ms", time.ticks_diff(time.ticks_ms(), start))
finally:
    for name in ("stress.tmp", "stress.json"):
        try:
            os.remove(name)
        except OSError:
            pass
print("STRESS_DONE cycles={} ms={}".format(done, time.ticks_diff(time.ticks_ms(), start)))
