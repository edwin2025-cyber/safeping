"""SafePing field logger (runs on the LAPTOP, not on a board).

Reads the Fob (COM15) and the Relay (COM14) at the same time and saves one set of
files per test run:

  logs/<date>/<time>_<label>/<date>_<time>_<label>_raw.txt      every line, with laptop time
  logs/<date>/<time>_<label>/<date>_<time>_<label>_alerts.csv   one row per alert (ctr)
  logs/<date>/<time>_<label>/<date>_<time>_<label>_summary.txt  sent, received, lost, signal
  logs/README.md is the index of every run. Add a row after each real test.

The raw file is written line by line, and the CSV and summary are rewritten after
every alert, so a crash or a dead laptop battery loses almost nothing.

Before you run it
  * Close Thonny. Only one program can hold a COM port.
  * The Fob must have the Fob program saved as main.py.
  * The Relay must have firmware/relay/main.py saved as main.py.

Run it (from the safeping-bench folder):
  python tests/field_log.py --label spotA
Stop it with Ctrl+C. The summary prints at the end.

How a lost packet is found
  The Fob prints SAFEPING_MSG with the counter (ctr) before it sends. The Relay prints
  SAFEPING_MSG when it hears one. A ctr the Fob sent over LoRa that the Relay never
  printed is counted as lost.
"""
import argparse
import csv
import json
import queue
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import serial  # pyserial
except ImportError:
    serial = None

RELAY_INFO = re.compile(r"signal\s+(-?\d+)\s*dBm,\s*snr\s+(-?[\d.]+)")
WAIT_FOR_RELAY_S = 5      # warn if the Relay has not printed an alert this long after the Fob sent it

CSV_COLUMNS = [
    "ctr", "type", "fob_time", "fob_result", "relay_time", "received", "delay_s",
    "lat", "lon", "acc_m", "lat_deg", "lon_deg", "rssi_dbm", "snr_db", "same_message",
    "lora_retry", "p_pa", "t_c", "bat_pct", "confirmed", "ack_try",
]


def now_text(t):
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def micro_to_deg(e6):
    if e6 is None:
        return ""
    sign = "-" if e6 < 0 else ""
    e6 = abs(int(e6))
    return "{}{}.{:06d}".format(sign, e6 // 1000000, e6 % 1000000)


class Session:
    """Keeps track of every alert. Knows nothing about serial ports, so it can be tested alone."""

    def __init__(self, label, base_path):
        self.label = label
        self.base = base_path
        self.start = time.time()
        self.fob = {}             # ctr -> dict with Fob side
        self.relay = {}           # ctr -> dict with Relay side
        self.order = []           # ctrs in the order they first showed up
        self.last_fob_ctr = None
        self.relay_waiting = None # SAFEPING_MSG seen on the Relay, waiting for its "from ..." line
        self.not_safeping = 0
        self.duplicates = 0
        self.acks_rejected = 0
        self.cancelled = 0
        self.warned = set()
        self.notes = []

    # ---------- Fob lines ----------
    def fob_line(self, t, line):
        if line.startswith("SAFEPING_MSG "):
            msg = self._json(line)
            if msg is None or "ctr" not in msg:
                self.notes.append("{} Fob printed a SAFEPING_MSG line that is not valid JSON".format(now_text(t)))
                return None
            ctr = msg["ctr"]
            self.fob[ctr] = {"time": t, "msg": msg, "raw": line[13:], "result": "waiting"}
            self._seen(ctr)
            self.last_fob_ctr = ctr
            return "FOB  sent ctr {} {}{}".format(ctr, msg.get("type"), self._gps_text(msg))
        if self.last_fob_ctr is not None and self.last_fob_ctr in self.fob:
            entry = self.fob[self.last_fob_ctr]
            if line.startswith("sent over LoRa"):
                entry["result"] = "LoRa"
                entry["confirmed"] = "confirmed" in line
                return None
            if line.startswith("ACK received"):
                entry["ack_try"] = line.split("try")[-1].strip(" )")
                return "FOB  " + line
            if line.startswith("ACK missing"):
                entry["ack_missing"] = entry.get("ack_missing", 0) + 1
                return "FOB  " + line
            if line.startswith("ACK rejected") or line.startswith("ACK not checked"):
                if line.startswith("ACK rejected"):
                    self.acks_rejected += 1
                return "FOB  " + line
            if line.startswith("NOT CONFIRMED"):
                entry["result"] = "not confirmed"
                return "FOB  NOT CONFIRMED ctr {} (no ack from the Relay)".format(self.last_fob_ctr)
            if line.startswith("sent ") and " ctr " in line:
                entry["result"] = "WiFi"
                return None
            if line.startswith("NOT SENT"):
                entry["result"] = "NOT SENT"
                return "FOB  NOT SENT ctr {}".format(self.last_fob_ctr)
            if line.startswith("LoRa"):      # failures, the radio check, and the retry
                if line.startswith("LoRa failed"):
                    entry["result"] = "LoRa failed"
                entry["retried"] = True
                return "FOB  " + line
        if line.startswith("CANCELLED"):
            self.cancelled += 1
            return "FOB  " + line
        if line.startswith("Traceback") or "Error" in line or line.startswith("LoRa"):
            return "FOB  " + line
        return None

    # ---------- Relay lines ----------
    def relay_line(self, t, line):
        if line.startswith("SAFEPING_MSG "):
            msg = self._json(line)
            self.relay_waiting = (t, msg, line[13:])
            return None
        if line.startswith("from ") and self.relay_waiting:
            t0, msg, raw = self.relay_waiting
            self.relay_waiting = None
            if msg is None or "ctr" not in msg:
                return None
            m = RELAY_INFO.search(line)
            rssi = int(m.group(1)) if m else None
            snr = float(m.group(2)) if m else None
            ctr = msg["ctr"]
            self.relay[ctr] = {"time": t0, "msg": msg, "raw": raw, "rssi": rssi, "snr": snr}
            self._seen(ctr)
            text = "RELAY got  ctr {} {} signal {} dBm snr {}".format(ctr, msg.get("type"), rssi, snr)
            if "p" in msg:
                text += "  p {} Pa".format(msg["p"])
            return text
        if line.startswith("ignored a packet"):
            self.not_safeping += 1
            return "RELAY heard a packet that is not a SafePing alert"
        if line.startswith("duplicate of"):
            self.duplicates += 1
            return "RELAY " + line
        if line.startswith("Relay could not") or line.startswith("no ack key"):
            return "RELAY " + line
        if line.startswith("Traceback") or "Error" in line or "Relay radio" in line:
            return "RELAY " + line
        return None

    # ---------- checks ----------
    def overdue(self, t):
        """Fob alerts sent over LoRa that the Relay still has not printed."""
        out = []
        for ctr, f in self.fob.items():
            if ctr in self.relay or ctr in self.warned or f["result"] != "LoRa":
                continue
            if t - f["time"] >= WAIT_FOR_RELAY_S:
                self.warned.add(ctr)
                out.append("CHECK no Relay receipt for ctr {} after {} s".format(ctr, WAIT_FOR_RELAY_S))
        return out

    def rows(self):
        rows = []
        for ctr in self.order:
            f = self.fob.get(ctr)
            r = self.relay.get(ctr)
            msg = (f or r)["msg"]
            delay = ""
            if f and r:
                delay = "{:.2f}".format(r["time"] - f["time"])
            same = ""
            if f and r:
                same = "yes" if f["raw"] == r["raw"] else "NO"
            rows.append({
                "ctr": ctr,
                "type": msg.get("type", ""),
                "fob_time": now_text(f["time"]) if f else "",
                "fob_result": f["result"] if f else "not in Fob log",
                "relay_time": now_text(r["time"]) if r else "",
                "received": "yes" if r else "no",
                "delay_s": delay,
                "lat": msg.get("lat", ""),
                "lon": msg.get("lon", ""),
                "acc_m": msg.get("acc", ""),
                "lat_deg": micro_to_deg(msg.get("lat")),
                "lon_deg": micro_to_deg(msg.get("lon")),
                "rssi_dbm": r["rssi"] if r and r["rssi"] is not None else "",
                "snr_db": r["snr"] if r and r["snr"] is not None else "",
                "same_message": same,
                "lora_retry": "yes" if f and f.get("retried") else "",
                "p_pa": msg.get("p", ""),
                "t_c": "{:.2f}".format(msg["t"] / 100) if "t" in msg else "",
                "bat_pct": msg.get("bat", ""),
                "confirmed": ("yes" if f.get("confirmed") else "no") if f and f["result"] in ("LoRa", "not confirmed") else "",
                "ack_try": f.get("ack_try", "") if f else "",
            })
        return rows

    def summary(self, end_t):
        sent_lora = [c for c, f in self.fob.items() if f["result"] in ("LoRa", "not confirmed")]
        confirmed = [c for c, f in self.fob.items() if f.get("confirmed")]
        unconfirmed = sorted(c for c, f in self.fob.items() if f["result"] == "not confirmed")
        unconfirmed_but_heard = [c for c in unconfirmed if c in self.relay]
        needed_resend = sorted(c for c, f in self.fob.items() if f.get("ack_missing"))
        not_sent = [c for c, f in self.fob.items() if f["result"] in ("NOT SENT", "LoRa failed")]
        lost = sorted(c for c in sent_lora if c not in self.relay)
        relay_only = sorted(c for c in self.relay if c not in self.fob)
        changed = sorted(c for c in self.relay if c in self.fob and self.fob[c]["raw"] != self.relay[c]["raw"])
        rssi = [r["rssi"] for r in self.relay.values() if r["rssi"] is not None]
        snr = [r["snr"] for r in self.relay.values() if r["snr"] is not None]
        delays = [self.relay[c]["time"] - self.fob[c]["time"] for c in self.relay if c in self.fob]
        with_gps = [c for c, f in self.fob.items() if "lat" in f["msg"]]
        received = len([c for c in sent_lora if c in self.relay])
        retried = sorted(c for c, f in self.fob.items() if f.get("retried"))

        lines = [
            "SafePing field test summary",
            "label: {}".format(self.label),
            "start: {}".format(now_text(self.start)),
            "end:   {}".format(now_text(end_t)),
            "length: {:.0f} s".format(end_t - self.start),
            "",
            "Fob alerts printed:          {}".format(len(self.fob)),
            "  sent over LoRa:            {}".format(len(sent_lora)),
            "  not sent (Fob said so):    {}{}".format(len(not_sent), self._list(not_sent)),
            "  cancelled taps:            {}".format(self.cancelled),
            "  LoRa had a problem:        {}{}".format(len(retried), self._list(retried)),
            "  with a GPS position:       {}".format(len(with_gps)),
            "Relay received (of LoRa):    {} of {}".format(received, len(sent_lora)),
            "Confirmed by ack:            {} of {}".format(len(confirmed), len(sent_lora)),
            "  needed a resend:           {}{}".format(len(needed_resend), self._list(needed_resend)),
            "  NOT confirmed:             {}{}".format(len(unconfirmed), self._list(unconfirmed)),
            "  not confirmed but Relay had it (ack lost): {}".format(len(unconfirmed_but_heard)),
            "Duplicates at the Relay:     {}".format(self.duplicates),
            "Fake or wrong acks rejected: {}".format(self.acks_rejected),
            "LOST (sent, never heard):    {}{}".format(len(lost), self._list(lost)),
            "Relay only (not in Fob log): {}{}".format(len(relay_only), self._list(relay_only)),
            "Changed on the way:          {}{}".format(len(changed), self._list(changed)),
            "Not-SafePing packets heard:  {}".format(self.not_safeping),
            "",
            "Signal (dBm):  {}".format(self._range(rssi, "{:.0f}")),
            "SNR (dB):      {}".format(self._range(snr, "{:.2f}")),
            "Fob print to Relay print (s): {}".format(self._range(delays, "{:.2f}")),
            "  (laptop clock for both. Starts when the Fob prints, after any cancel window.)",
        ]
        if self.notes:
            lines += ["", "Notes:"] + ["  " + n for n in self.notes]
        return "\n".join(lines) + "\n"

    def save(self, end_t=None):
        end_t = end_t or time.time()
        with open(str(self.base) + "_alerts.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            w.writerows(self.rows())
        with open(str(self.base) + "_summary.txt", "w") as f:
            f.write(self.summary(end_t))

    # ---------- helpers ----------
    def _seen(self, ctr):
        if ctr not in self.order:
            self.order.append(ctr)

    @staticmethod
    def _json(line):
        try:
            msg = json.loads(line[13:])
            return msg if isinstance(msg, dict) else None
        except ValueError:
            return None

    @staticmethod
    def _gps_text(msg):
        if "lat" in msg:
            text = "  GPS {}, {} acc {} m".format(micro_to_deg(msg["lat"]), micro_to_deg(msg["lon"]), msg.get("acc"))
        else:
            text = "  no GPS"
        if "p" in msg:
            text += "  p {} Pa".format(msg["p"])
        if "t" in msg:
            text += "  t {:.2f} C".format(msg["t"] / 100)
        if "bat" in msg:
            text += "  bat {}%".format(msg["bat"])
        return text

    @staticmethod
    def _list(items):
        return "  (ctr {})".format(", ".join(str(i) for i in items)) if items else ""

    @staticmethod
    def _range(values, fmt):
        if not values:
            return "none"
        return "min {}  max {}  avg {}".format(fmt.format(min(values)), fmt.format(max(values)),
                                              fmt.format(sum(values) / len(values)))


def reader(name, port, q, stop):
    """Read lines from one board and put them on the queue. Reconnects if the cable is bumped."""
    while not stop.is_set():
        try:
            ser = serial.Serial()
            ser.port = port
            ser.baudrate = 115200
            ser.timeout = 0.2
            ser.dtr = False           # keeps the board from resetting when the port opens
            ser.rts = False
            ser.open()
            q.put((time.time(), "INFO", "{} connected on {}".format(name, port)))
            buf = b""
            while not stop.is_set():
                buf += ser.read(ser.in_waiting or 1)
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    q.put((time.time(), name, raw.decode("utf-8", errors="replace").strip()))
        except Exception as err:      # port busy, unplugged, or wrong name
            q.put((time.time(), "INFO", "{} problem on {}: {}. Retrying in 2 s".format(name, port, err)))
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description="Log the Fob and the Relay during a field test.")
    parser.add_argument("--label", default="test", help="short name for this run, like spotA")
    parser.add_argument("--fob", default="COM15")
    parser.add_argument("--relay", default="COM14")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "logs"))
    args = parser.parse_args()

    if serial is None:
        print("pyserial is not installed. Run: python -m pip install pyserial")
        sys.exit(1)

    label = re.sub(r"[^A-Za-z0-9_-]", "_", args.label)
    now = datetime.now()
    run_dir = Path(args.out) / now.strftime("%Y-%m-%d") / "{}_{}".format(now.strftime("%H%M%S"), label)
    run_dir.mkdir(parents=True, exist_ok=True)          # logs/<date>/<time>_<label>/
    base = run_dir / "{}_{}".format(now.strftime("%Y-%m-%d_%H%M%S"), label)
    session = Session(label, base)

    q = queue.Queue()
    stop = threading.Event()
    for name, port in (("FOB", args.fob), ("RELAY", args.relay)):
        threading.Thread(target=reader, args=(name, port, q, stop), daemon=True).start()

    print("Logging to", str(base) + "_*")
    print("Fob on", args.fob, " Relay on", args.relay, " Ctrl+C to stop")
    raw_file = open(str(base) + "_raw.txt", "a", encoding="utf-8")
    raw_file.write("# label {}  fob {}  relay {}\n".format(label, args.fob, args.relay))

    try:
        while True:
            try:
                t, src, line = q.get(timeout=0.2)
            except queue.Empty:
                for warn in session.overdue(time.time()):
                    print(now_text(time.time())[11:19], warn)
                continue
            raw_file.write("{} {:<5} {}\n".format(now_text(t), src, line))
            raw_file.flush()
            if src == "INFO":
                shown = line
            elif src == "FOB":
                shown = session.fob_line(t, line)
            else:
                shown = session.relay_line(t, line)
            if shown:
                print(now_text(t)[11:19], shown)
                session.save()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        end = time.time()
        raw_file.close()
        session.save(end)
        print()
        print(session.summary(end))
        print("Files saved:", str(base) + "_raw.txt, _alerts.csv, _summary.txt")


if __name__ == "__main__":
    main()
