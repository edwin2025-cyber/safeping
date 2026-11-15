"""Survey mode on the Fob (message-format.md, "Survey points").

With SURVEY_MODE = True, a single press makes a survey point instead of a STATUS alert.
This file holds the parts that need no pins, so tests/test_survey.py runs them:

  ap_list(scan)        WLAN.scan() results as the message's "aps" list, strongest first
  message(...)         the SURVEY message before it is signed
  point_line(...)      the SURVEY_POINT log line for tests/field_log.py
  SurveyStore          signed points waiting for WiFi, one file each in survey_q/

Store: one file per point (survey_q/<ctr>.json), so RAM only ever holds one point
(a point with 15 access points is about 1 KB) and each write is small. Each file is
written as <ctr>.json.tmp in full, then renamed, so a crash leaves the old state or the
new one, never half a point. A .tmp left behind by a crash is removed at load().
"""
import binascii

try:
    import os
except ImportError:                                       # pragma: no cover
    os = None

TOP_APS = 15
SSID_MAX_BYTES = 32


def _hex(value):
    if isinstance(value, str):
        value = value.encode()
    return binascii.hexlify(bytes(value)).decode()


def ap_list(scan, top=TOP_APS):
    """scan: WLAN.scan() entries (ssid, bssid, channel, rssi, security, hidden).
    Returns [[bssid_hex, rssi, channel, ssid_hex], ...], one per BSSID (its strongest),
    strongest first, at most top. Entries that do not parse are skipped."""
    best = {}
    for entry in scan:
        try:
            ssid, bssid, ch, rssi = entry[0], entry[1], int(entry[2]), int(entry[3])
            b = _hex(bssid)
            raw = ssid.encode() if isinstance(ssid, str) else bytes(ssid)
            s = _hex(raw[:SSID_MAX_BYTES])
        except Exception:
            continue
        if len(b) != 12:
            continue
        rssi = max(-127, min(0, rssi))
        ch = max(0, min(255, ch))
        if b not in best or rssi > best[b][1]:
            best[b] = [b, rssi, ch, s]
    aps = sorted(best.values(), key=lambda a: (-a[1], a[0]))
    return aps[:top]


def message(device_id, ctr, ts, pressure, gps, sats, bat, aps):
    """The SURVEY message, not signed yet. Fields with no value are left out.
    pressure: baro.Window.result() or None. gps: (lat_e6, lon_e6, acc_m) or None."""
    msg = {"v": 1, "id": device_id, "type": "SURVEY", "ctr": ctr}
    if ts is not None:
        msg["ts"] = ts
    if gps:
        msg["lat"], msg["lon"], msg["acc"] = int(gps[0]), int(gps[1]), int(gps[2])
    if pressure:
        msg["p"] = pressure["p"]
        if pressure.get("t") is not None:
            msg["t"] = pressure["t"]
    if bat is not None:
        msg["bat"] = int(bat)
    if pressure:
        msg["pd"] = pressure["pd"]
    msg["n"] = pressure["n"] if pressure else 0
    msg["fix"] = 1 if gps else 0
    msg["sats"] = max(0, min(99, int(sats or 0)))
    msg["aps"] = aps
    return msg


def point_line(n, msg, sent):
    """SURVEY_POINT n=3 ctr=512 p=98760.3 samples=15 fix=0 sats=3 aps=12 sent=wifi
    n is the point number since boot. sent: wifi, stored or failed."""
    pd = msg.get("pd")
    p = "-" if pd is None else "{}.{}".format(pd // 10, pd % 10)
    return "SURVEY_POINT n={} ctr={} p={} samples={} fix={} sats={} aps={} sent={}".format(
        n, msg["ctr"], p, msg.get("n", 0), msg.get("fix", 0), msg.get("sats", 0),
        len(msg.get("aps") or []), sent)


class SurveyStore:
    def __init__(self, folder="survey_q", max_points=100, files=None):
        self.folder = folder
        self.max = max_points
        self.files = files or _Files()
        self.ctrs = []                  # counters waiting, oldest first (RAM, read at load())

    def __len__(self):
        return len(self.ctrs)

    def _path(self, name):
        return self.folder + "/" + name

    def load(self):
        """Read the folder (boot only). Makes it if missing. Returns the points waiting."""
        self.files.makedir(self.folder)
        ctrs = []
        for name in self.files.listdir(self.folder):
            if name.endswith(".tmp"):
                self.files.remove(self._path(name))      # half a write from a crash
            elif name.endswith(".json"):
                try:
                    ctrs.append(int(name[:-5]))
                except ValueError:
                    pass
        self.ctrs = sorted(ctrs)
        return len(self.ctrs)

    def add(self, ctr, payload):
        """Save one signed point. Returns "stored", or "full" (nothing written).
        Raises if the flash write fails."""
        if ctr in self.ctrs:
            return "stored"
        if len(self.ctrs) >= self.max:
            return "full"
        name = "{}.json".format(ctr)
        tmp = self._path(name + ".tmp")
        self.files.write(tmp, payload)
        self.files.replace(tmp, self._path(name))
        self.ctrs.append(ctr)
        self.ctrs.sort()
        return "stored"

    def oldest(self):
        return self.ctrs[0] if self.ctrs else None

    def read(self, ctr):
        """The signed payload text, or None if the file is gone or unreadable."""
        return self.files.read(self._path("{}.json".format(ctr)))

    def remove(self, ctr):
        """Forget one point (sent, or unreadable)."""
        self.files.remove(self._path("{}.json".format(ctr)))
        if ctr in self.ctrs:
            self.ctrs.remove(ctr)


class _Files:
    """The board's (or laptop's) files. Tests swap this for a fake."""

    def makedir(self, name):
        try:
            os.mkdir(name)
        except OSError:
            pass                                 # already there

    def listdir(self, name):
        try:
            return os.listdir(name)
        except OSError:
            return []

    def read(self, name):
        try:
            with open(name) as f:
                return f.read()
        except OSError:
            return None

    def write(self, name, text):
        with open(name, "w") as f:
            f.write(text)

    def replace(self, src, dst):
        try:
            os.rename(src, dst)              # littlefs replaces dst in one step
        except OSError:
            try:
                os.remove(dst)
            except OSError:
                pass
            os.rename(src, dst)

    def remove(self, name):
        try:
            os.remove(name)
        except OSError:
            pass
