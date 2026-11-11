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

Run it (from the safeping folder):
  python tests/field_log.py --label spotA --relay COM14          Fob and Relay
  python tests/field_log.py --label spotA --relay COM14 --no-fob  Relay only
  python tests/field_log.py --label spotA                         Fob only
Add --forward to also send each Relay alert to the server, the same way
server/serial_bridge.py does, so the website shows them during the test.
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
    "path", "result", "ms", "reason",          # from the Fob's SEND_RESULT line
    "retry_tries", "retry_result",             # from RETRY_* lines (retry queue)
    "help_ms",                                 # from HELP_RECEIVED: ms after the confirm
]
# Fob lines that mean the LoRa radio had trouble during a send. "LoRa fallback on" and
# "LoRa acks: ..." are boot lines, not problems.
LORA_PROBLEM = ("LoRa failed", "LoRa check", "LoRa: setting the radio up again", "LoRa worked after")
RETRY_TAGS = ("RETRY_QUEUED", "RETRY_TRY", "RETRY_DONE", "RETRY_GAVE_UP", "RETRY_STOPPED")
HELP_TAGS = ("HELP_RECEIVED", "HELP_TIMEOUT", "HELP_LISTEN", "HELP ignored", "HELP_LISTEN_END")


def parse_send_result(line):
    """The fields of a Fob 'SEND_RESULT ctr=.. kind=.. path=.. result=.. ms=.. reason=..' line."""
    out = {}
    for part in line.split()[1:]:
        if "=" in part:
            name, value = part.split("=", 1)
            out[name] = value
    return out


MSG_PREFIX = "SAFEPING_MSG "


def msg_text(line):
    """The JSON after the LAST "SAFEPING_MSG " in a line (same rule as
    server/serial_bridge.message_text). A board can put bytes left over from an earlier
    print in front of a message (64 bytes from the Relay on 2026-11-11, selfcheck_b4)."""
    at = line.rfind(MSG_PREFIX)
    return None if at < 0 else line[at + len(MSG_PREFIX):]


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

    def __init__(self, label, base_path, fob_logged=True, relay_logged=True):
        self.label = label
        self.base = base_path
        self.fob_logged = fob_logged   # False with --no-fob: Relay only, Fob columns stay empty
        self.relay_logged = relay_logged   # False without --relay: Fob only, Relay columns stay empty
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
        self.self_checks = []     # one dict per SELF_CHECK line (one per boot)
        self.boots = {}           # ctr -> BOOT message and its SEND_RESULT
        self.retry = {}           # ctr -> {"queued", "tries", "result", "reason"}
        self.retry_stopped = 0
        self.help = {}            # ctr -> ms after confirm
        self.help_timeouts = []
        self.help_ignored = 0

    # ---------- Fob lines ----------
    def fob_line(self, t, line):
        if line.startswith("SAFEPING_MSG "):
            msg = self._json(line)
            if msg is None or "ctr" not in msg:
                self.notes.append("{} Fob printed a SAFEPING_MSG line that is not valid JSON".format(now_text(t)))
                return None
            ctr = msg["ctr"]
            if msg.get("type") == "BOOT":            # a boot report, not an alert
                self.boots[ctr] = {"time": t, "msg": msg}
                self.last_fob_ctr = ctr
                return "FOB  boot report ctr {} fail={} fw={}".format(ctr, msg.get("fail"), msg.get("fw"))
            self.fob[ctr] = {"time": t, "msg": msg, "raw": msg_text(line), "result": "waiting"}
            self._seen(ctr)
            self.last_fob_ctr = ctr
            return "FOB  sent ctr {} {}{}".format(ctr, msg.get("type"), self._gps_text(msg))
        if line.startswith("SEND_RESULT "):
            fields = parse_send_result(line)
            try:
                ctr = int(fields.get("ctr", ""))
            except ValueError:
                ctr = None
            if ctr in self.boots:
                self.boots[ctr]["send"] = fields
            elif "try" in fields:                    # a retry: the first result stays as it was
                if ctr in self.retry:
                    self.retry[ctr]["last"] = fields
            elif ctr in self.fob:
                self.fob[ctr]["send"] = fields
            return "FOB  " + line
        if line.startswith("SafePing Fob "):
            # A new boot. The boot lines that follow ("LoRa fallback on", "LoRa acks: ...")
            # belong to no alert. Before 2026-11-11 they were counted as "LoRa had a problem"
            # for the last alert before the reboot (ctr 248, 250, 252, 254 in crashtest).
            self.last_fob_ctr = None
            return "FOB  " + line
        if line.startswith("BOOT_STOPPED "):
            ctr = self._ctr_of(line)
            if ctr in self.boots:
                self.boots[ctr]["stopped"] = True
            return "FOB  " + line
        if line.startswith("BOOT report stopped by a button press"):   # firmware before 2026.11.11c
            if self.last_fob_ctr in self.boots:
                self.boots[self.last_fob_ctr]["stopped"] = True
            return "FOB  " + line
        if line.startswith("BOOT_RESEND "):
            ctr = self._ctr_of(line)
            if ctr in self.boots:
                self.boots[ctr]["resent"] = True
            self.last_fob_ctr = None             # the lines that follow are about the BOOT report
            return "FOB  " + line
        if line.startswith("SELF_CHECK "):
            self.self_checks.append(parse_send_result(line))
            return "FOB  " + line
        if line.startswith(RETRY_TAGS):
            self._retry_line(line)
            return "FOB  " + line
        if line.startswith(HELP_TAGS):
            self._help_line(line)
            return "FOB  " + line
        if line.startswith("falling back to LoRa") or line.startswith("no ack from server"):
            return "FOB  " + line
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
            if line.startswith(LORA_PROBLEM):  # failures, the radio check, and the radio reset
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

    @staticmethod
    def _ctr_of(line):
        try:
            return int(parse_send_result(line).get("ctr", ""))
        except ValueError:
            return None

    def _retry_line(self, line):
        tag = line.split()[0]
        fields = parse_send_result(line)
        try:
            ctr = int(fields.get("ctr", ""))
        except ValueError:
            return
        r = self.retry.setdefault(ctr, {"tries": 0, "result": "queued", "reason": fields.get("reason", "")})
        if tag == "RETRY_TRY":
            r["tries"] = int(fields.get("try", r["tries"] + 1))
            self.last_fob_ctr = None             # the lines that follow are about the retry
        elif tag == "RETRY_DONE":
            r["result"] = "got through"
        elif tag == "RETRY_GAVE_UP":
            r["result"] = "gave up ({})".format(fields.get("reason", "-"))
        elif tag == "RETRY_STOPPED":
            self.retry_stopped += 1

    def _help_line(self, line):
        fields = parse_send_result(line)
        if line.startswith("HELP_RECEIVED"):
            try:
                self.help[int(fields["ctr"])] = int(fields.get("ms_after_confirm", 0))
            except (KeyError, ValueError):
                pass
        elif line.startswith("HELP_TIMEOUT"):
            self.help_timeouts.append(fields.get("ctr", "?"))
        elif line.startswith("HELP ignored"):
            self.help_ignored += 1

    # ---------- Relay lines ----------
    def relay_line(self, t, line):
        if line.startswith("SAFEPING_MSG "):
            msg = self._json(line)
            if line.rfind(MSG_PREFIX) > 0:
                self.notes.append("{} Relay line had {} bytes left over in front of the message (ignored)".format(
                    now_text(t), line.rfind(MSG_PREFIX)))
            self.relay_waiting = (t, msg, msg_text(line))
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
        if not self.relay_logged:
            return out
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
                "fob_result": f["result"] if f else ("not in Fob log" if self.fob_logged else ""),
                "relay_time": now_text(r["time"]) if r else "",
                "received": ("yes" if r else "no") if self.relay_logged else "",
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
                "confirmed": self._confirmed_text(f),
                "ack_try": f.get("ack_try", "") if f else "",
                "path": f.get("send", {}).get("path", "") if f else "",
                "result": f.get("send", {}).get("result", "") if f else "",
                "ms": f.get("send", {}).get("ms", "") if f else "",
                "reason": f.get("send", {}).get("reason", "") if f else "",
                "retry_tries": self.retry[ctr]["tries"] if ctr in self.retry else "",
                "retry_result": self.retry[ctr]["result"] if ctr in self.retry else "",
                "help_ms": self.help.get(ctr, ""),
            })
        return rows

    def summary(self, end_t):
        if not self.fob_logged:
            return self._relay_summary(end_t)
        sent_wifi = sorted(c for c, f in self.fob.items() if self._path(f) == "wifi")
        sent_lora = [c for c, f in self.fob.items() if self._path(f) == "lora"]
        confirmed = sorted(c for c, f in self.fob.items() if self._is_confirmed(f))
        confirmed_wifi = [c for c in confirmed if self._path(self.fob[c]) == "wifi"]
        confirmed_lora = [c for c in confirmed if self._path(self.fob[c]) == "lora"]
        unconfirmed = sorted(c for c, f in self.fob.items()
                             if f["result"] == "not confirmed"
                             or f.get("send", {}).get("result") in ("not_confirmed", "failed"))
        unconfirmed_but_heard = [c for c in unconfirmed if c in self.relay]
        needed_resend = sorted(c for c, f in self.fob.items() if f.get("ack_missing"))
        not_sent = [c for c, f in self.fob.items() if f["result"] in ("NOT SENT", "LoRa failed")]
        lost = sorted(c for c in sent_lora if c not in self.relay) if self.relay_logged else []
        relay_only = sorted(c for c in self.relay if c not in self.fob)
        changed = sorted(c for c in self.relay if c in self.fob and self.fob[c]["raw"] != self.relay[c]["raw"])
        rssi = [r["rssi"] for r in self.relay.values() if r["rssi"] is not None]
        snr = [r["snr"] for r in self.relay.values() if r["snr"] is not None]
        delays = [self.relay[c]["time"] - self.fob[c]["time"] for c in self.relay if c in self.fob]
        with_gps = [c for c, f in self.fob.items() if "lat" in f["msg"]]
        received = len([c for c in sent_lora if c in self.relay])
        retried = sorted(c for c, f in self.fob.items() if f.get("retried"))
        sent_any = len(sent_wifi) + len(sent_lora)
        send_ms = [int(f["send"]["ms"]) for f in self.fob.values()
                   if f.get("send", {}).get("ms", "").isdigit()]
        reasons = {}
        for f in self.fob.values():
            reason = f.get("send", {}).get("reason")
            if reason and reason != "-":
                reasons[reason] = reasons.get(reason, 0) + 1
        relay_text = "{} of {}".format(received, len(sent_lora)) if self.relay_logged \
            else "unknown (Relay not logged, use --relay)"

        lines = [
            "SafePing field test summary",
            "label: {}".format(self.label),
            "start: {}".format(now_text(self.start)),
            "end:   {}".format(now_text(end_t)),
            "length: {:.0f} s".format(end_t - self.start),
            "",
            "Fob alerts printed:          {}".format(len(self.fob)),
            "  sent over WiFi:            {}".format(len(sent_wifi)),
            "  sent over LoRa:            {}".format(len(sent_lora)),
            "  not sent (Fob said so):    {}{}".format(len(not_sent), self._list(not_sent)),
            "  cancelled taps:            {}".format(self.cancelled),
            "  LoRa had a problem:        {}{}".format(len(retried), self._list(retried)),
            "  with a GPS position:       {}".format(len(with_gps)),
            "Relay received (of LoRa):    {}".format(relay_text),
            "Confirmed:                   {} of {}  (WiFi {}, LoRa {})".format(
                len(confirmed), sent_any, len(confirmed_wifi), len(confirmed_lora)),
            "  LoRa needed a resend:      {}{}".format(len(needed_resend), self._list(needed_resend)),
            "  NOT confirmed:             {}{}".format(len(unconfirmed), self._list(unconfirmed)),
            "  not confirmed but Relay had it (ack lost): {}".format(len(unconfirmed_but_heard)),
            "WiFi not used, by reason:    {}".format(
                ", ".join("{} {}".format(r, n) for r, n in sorted(reasons.items())) or "none"),
            "Duplicates at the Relay:     {}".format(self.duplicates),
            "Fake or wrong acks rejected: {}".format(self.acks_rejected),
            "LOST (sent, never heard):    {}{}".format(len(lost), self._list(lost)),
            "Relay only (not in Fob log): {}{}".format(len(relay_only), self._list(relay_only)),
            "Changed on the way:          {}{}".format(len(changed), self._list(changed)),
            "Not-SafePing packets heard:  {}".format(self.not_safeping),
            "",
            "Send time (ms):  {}".format(self._range(send_ms, "{:.0f}")),
            "  (from SEND_RESULT: the send decision to the result, after any cancel window.)",
            "Signal (dBm):  {}".format(self._range(rssi, "{:.0f}")),
            "SNR (dB):      {}".format(self._range(snr, "{:.2f}")),
            "Fob print to Relay print (s): {}".format(self._range(delays, "{:.2f}")),
            "  (laptop clock for both. Starts when the Fob prints, after any cancel window.)",
            "",
        ] + self._extra_lines()
        if self.notes:
            lines += ["", "Notes:"] + ["  " + n for n in self.notes]
        return "\n".join(lines) + "\n"

    def _extra_lines(self):
        """Self-check, boot reports, retry queue and help messages."""
        lines = []
        if self.self_checks:
            for i, sc in enumerate(self.self_checks, 1):
                failed = [k for k, v in sc.items() if v == "fail" and k != "wifi"]
                lines.append("Self-check {}:                {}  (wifi {}, reset {}, fw {})".format(
                    i, "all passed" if not failed else "FAILED " + ", ".join(failed),
                    sc.get("wifi", "?"), sc.get("reset", "not reported (firmware before 2026.11.11b)"),
                    sc.get("fw", "?")))
        else:
            lines.append("Self-check:                  none seen (no boot during the log)")
        confirmed = [c for c, b in self.boots.items() if b.get("send", {}).get("result") == "confirmed"]
        lines.append("Boot reports:                {} made, {} confirmed".format(len(self.boots), len(confirmed)))
        stopped = sorted(c for c, b in self.boots.items() if b.get("stopped"))
        later = [c for c in stopped if self.boots[c].get("resent") and c in confirmed]
        waiting = [c for c in stopped if c not in later]
        lines.append("  stopped by a press, sent later: {}{}".format(len(later), self._list(later)))
        lines.append("  stopped by a press, not sent yet: {}{}".format(len(waiting), self._list(waiting)))
        done = sorted(c for c, r in self.retry.items() if r["result"] == "got through")
        gave_up = sorted(c for c, r in self.retry.items() if r["result"].startswith("gave up"))
        waiting = sorted(c for c, r in self.retry.items() if r["result"] == "queued")
        lines += [
            "Retry queue:                 {} queued{}".format(len(self.retry), self._list(sorted(self.retry))),
            "  tries:                     {}".format(sum(r["tries"] for r in self.retry.values())),
            "  got through:               {}{}".format(len(done), self._list(done)),
            "  gave up:                   {}{}".format(len(gave_up), self._list(gave_up)),
            "  still waiting at the end:  {}{}".format(len(waiting), self._list(waiting)),
            "  stopped by a press:        {}".format(self.retry_stopped),
            "Help received (WiFi):        {}{}".format(len(self.help), self._list(sorted(self.help))),
            "  ms after the confirm:      {}".format(self._range(list(self.help.values()), "{:.0f}")),
            "  stopped listening (2 min): {}".format(len(self.help_timeouts)),
            "  wrong help messages ignored: {}".format(self.help_ignored),
        ]
        return lines

    def _relay_summary(self, end_t):
        """Summary for --no-fob runs. Nothing here needs the Fob log."""
        heard = sorted(self.relay)
        rssi = [r["rssi"] for r in self.relay.values() if r["rssi"] is not None]
        snr = [r["snr"] for r in self.relay.values() if r["snr"] is not None]
        with_gps = [c for c, r in self.relay.items() if "lat" in r["msg"]]
        lines = [
            "SafePing field test summary (Relay only, Fob not logged)",
            "label: {}".format(self.label),
            "start: {}".format(now_text(self.start)),
            "end:   {}".format(now_text(end_t)),
            "length: {:.0f} s".format(end_t - self.start),
            "",
            "Relay received alerts:       {}{}".format(len(heard), self._list(heard)),
            "  with a GPS position:       {}".format(len(with_gps)),
            "Duplicates at the Relay:     {}".format(self.duplicates),
            "Not-SafePing packets heard:  {}".format(self.not_safeping),
            "Sent, lost, confirmed:       unknown (no Fob log)",
            "",
            "Signal (dBm):  {}".format(self._range(rssi, "{:.0f}")),
            "SNR (dB):      {}".format(self._range(snr, "{:.2f}")),
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
    @staticmethod
    def _path(f):
        """"wifi", "lora", "none" or "" for one Fob alert. SEND_RESULT wins. Older logs
        without it fall back to the lines the Fob printed."""
        send = f.get("send")
        if send and send.get("path"):
            return send["path"]
        if f["result"] in ("LoRa", "not confirmed"):
            return "lora"
        if f["result"] == "WiFi":
            return "wifi"
        return ""

    @staticmethod
    def _is_confirmed(f):
        send = f.get("send")
        if send and send.get("result"):
            return send["result"] == "confirmed"
        return bool(f.get("confirmed")) or f["result"] == "WiFi"

    def _confirmed_text(self, f):
        if not f or self._path(f) not in ("wifi", "lora", "none"):
            return ""
        return "yes" if self._is_confirmed(f) else "no"

    def _seen(self, ctr):
        if ctr not in self.order:
            self.order.append(ctr)

    @staticmethod
    def _json(line):
        try:
            msg = json.loads(msg_text(line))
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


def reader(name, port, q, stop, quiet=False):
    """Read lines from one board and put them on the queue. Reconnects if the cable is bumped.

    quiet=True (used for the Fob): after a problem, print one line and then retry
    without printing every error. Print one line again when it comes back.
    """
    connected_once = False
    retrying = False              # True while a quiet reader is in its silent retry loop
    while not stop.is_set():
        try:
            ser = serial.Serial()
            ser.port = port
            ser.baudrate = 115200
            ser.timeout = 0.2
            ser.dtr = False           # keeps the board from resetting when the port opens
            ser.rts = False
            ser.open()
            if quiet and retrying and connected_once:
                q.put((time.time(), "INFO", "Fob reconnected"))
            else:
                q.put((time.time(), "INFO", "{} connected on {}".format(name, port)))
            connected_once = True
            retrying = False
            buf = b""
            while not stop.is_set():
                buf += ser.read(ser.in_waiting or 1)
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    q.put((time.time(), name, raw.decode("utf-8", errors="replace").strip()))
        except Exception as err:      # port busy, unplugged, or wrong name
            if not quiet:
                q.put((time.time(), "INFO", "{} problem on {}: {}. Retrying in 2 s".format(name, port, err)))
            elif not retrying:
                if connected_once:
                    q.put((time.time(), "INFO", "Fob disconnected, retrying quietly"))
                else:         # never connected: show the error once so a wrong COM name is visible
                    q.put((time.time(), "INFO", "{} problem on {}: {}. Retrying quietly".format(name, port, err)))
                retrying = True
            time.sleep(2)


SERVER_DIR = Path(__file__).resolve().parent.parent / "server"


def load_forwarder():
    """The serial bridge's own handle_line(), so --forward does exactly what
    server/serial_bridge.py does: each Relay SAFEPING_MSG line goes to processor.process()
    with source "lora", into the same database the website reads."""
    # First on the path, so server/config.py is the config the server modules import.
    sys.path.insert(0, str(SERVER_DIR))
    import db
    import serial_bridge
    db.init_db()
    return serial_bridge.handle_line


def main():
    parser = argparse.ArgumentParser(description="Log the Fob and the Relay during a field test.")
    parser.add_argument("--label", default="test", help="short name for this run, like spotA")
    parser.add_argument("--fob", default="COM15")
    parser.add_argument("--relay", default=None,
                        help="the Relay's port, like COM14. Left out: the Relay is not logged")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "logs"))
    parser.add_argument("--no-fob", action="store_true",
                        help="do not open the Fob port at all. Log only the Relay. Fob-only columns stay empty")
    parser.add_argument("--forward", action="store_true",
                        help="also send each Relay alert to the server, like serial_bridge.py "
                             "(the bridge cannot run while the logger holds the Relay port)")
    args = parser.parse_args()

    if serial is None:
        print("pyserial is not installed. Run: python -m pip install pyserial")
        sys.exit(1)
    if args.no_fob and not args.relay:
        print("Nothing to log: --no-fob needs --relay COM14 (or the Relay's port).")
        sys.exit(1)
    if args.forward and not args.relay:
        print("--forward needs --relay COM14 (or the Relay's port).")
        sys.exit(1)
    forward = None
    if args.forward:
        try:
            forward = load_forwarder()
        except Exception as err:
            print("--forward could not load the server code:", err)
            sys.exit(1)

    label = re.sub(r"[^A-Za-z0-9_-]", "_", args.label)
    now = datetime.now()
    run_dir = Path(args.out) / now.strftime("%Y-%m-%d") / "{}_{}".format(now.strftime("%H%M%S"), label)
    run_dir.mkdir(parents=True, exist_ok=True)          # logs/<date>/<time>_<label>/
    base = run_dir / "{}_{}".format(now.strftime("%Y-%m-%d_%H%M%S"), label)
    session = Session(label, base, fob_logged=not args.no_fob, relay_logged=bool(args.relay))

    q = queue.Queue()
    stop = threading.Event()
    if not args.no_fob:
        threading.Thread(target=reader, args=("FOB", args.fob, q, stop, True), daemon=True).start()
    if args.relay:
        threading.Thread(target=reader, args=("RELAY", args.relay, q, stop), daemon=True).start()

    fob_text = "not logged (--no-fob)" if args.no_fob else args.fob
    relay_text = args.relay or "not logged (no --relay)"
    print("Logging to", str(base) + "_*")
    print("Fob", fob_text, " Relay", relay_text, " Ctrl+C to stop")
    if forward:
        print("Forwarding Relay alerts to the server database (like serial_bridge.py)")
    raw_file = open(str(base) + "_raw.txt", "a", encoding="utf-8")
    raw_file.write("# label {}  fob {}  relay {}{}\n".format(
        label, "none" if args.no_fob else args.fob, args.relay or "none", "  forward on" if forward else ""))

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
                if forward:
                    try:
                        result = forward(line)
                    except Exception as err:       # one bad line must never stop the logger
                        result = {"ok": False, "reason": "forward error: {}".format(err)}
                    if result is not None:
                        raw_file.write("{} {:<5} {}\n".format(now_text(time.time()), "SERVR", result))
                        raw_file.flush()
                        print(now_text(time.time())[11:19], "SERVER", result)
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
