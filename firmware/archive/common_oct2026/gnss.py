"""GPS reader for the SparkFun SAM-M10Q breakout, over the Qwiic I2C connector.

The module sends text sentences ("NMEA") on its own, once a second, by default. Over I2C
you ask how many bytes are waiting, then read them. This file does three things:

    1. read the waiting bytes          (GNSS.update)
    2. check each sentence's checksum  (checksum_ok)
    3. pull out position, satellites and accuracy as whole numbers  (parse_sentence)

Numbers match message-format.md:
    lat, lon = microdegrees   (34.730123 degrees is 34730123)
    acc      = meters, a rough guess (see below)

Accuracy: the module reports HDOP, a quality number where lower is better. We turn it
into meters with  acc = HDOP x 5  (about 5 m per HDOP unit, a common rule of thumb).
It is a guess for the dashboard, not a measurement. Say so in the report.

Usage:
    gps = GNSS(i2c)
    while True:
        gps.update()
        fix = gps.fix()       # None until the module has a position
        time.sleep(1)
"""
ADDR = 0x42               # u-blox default I2C address
REG_BYTES_HI = 0xFD       # number of bytes waiting, high byte
REG_BYTES_LO = 0xFE       # ... low byte
REG_STREAM = 0xFF         # the data itself

METERS_PER_HDOP = 5


def checksum_ok(sentence):
    """sentence is text like '$GNGGA,....*47'. The checksum is the XOR of everything
    between the $ and the *, written as two hex digits."""
    if not sentence.startswith("$") or "*" not in sentence:
        return False
    body, _, given = sentence[1:].partition("*")
    value = 0
    for ch in body:
        value ^= ord(ch)
    try:
        return value == int(given[:2], 16)
    except ValueError:
        return False


def _to_microdegrees(text, hemisphere, degree_digits):
    """NMEA writes ddmm.mmmmm (latitude) or dddmm.mmmmm (longitude). Whole numbers only."""
    if not text or not hemisphere:
        return None
    try:
        degrees = int(text[:degree_digits])
        whole, _, frac = text[degree_digits:].partition(".")
        scale = 10 ** len(frac)
        minutes = int(whole) * scale + (int(frac) if frac else 0)    # minutes times scale
    except ValueError:
        return None
    # microdegrees = degrees * 1e6 + minutes / 60 * 1e6, rounded
    micro = degrees * 1000000 + (minutes * 1000000 + 30 * scale) // (60 * scale)
    return -micro if hemisphere in ("S", "W") else micro


def parse_sentence(sentence):
    """Returns a dict, or None if it is not a sentence we use.

    GGA: position, fix quality, satellites, HDOP.
    RMC: whether the position is valid (A) or not (V)."""
    if not checksum_ok(sentence):
        return None
    fields = sentence[1:].split("*")[0].split(",")
    kind = fields[0][2:]                 # drop the two-letter talker, like GN or GP
    if kind == "GGA" and len(fields) >= 10:
        quality = int(fields[6]) if fields[6].isdigit() else 0
        result = {"kind": "GGA", "quality": quality,
                  "sats": int(fields[7]) if fields[7].isdigit() else 0}
        if fields[8]:
            tenths = fields[8].partition(".")
            result["hdop_x10"] = int(tenths[0]) * 10 + (int(tenths[2][:1]) if tenths[2] else 0)
        if quality > 0:
            result["lat"] = _to_microdegrees(fields[2], fields[3], 2)
            result["lon"] = _to_microdegrees(fields[4], fields[5], 3)
        return result
    if kind == "RMC" and len(fields) >= 3:
        return {"kind": "RMC", "valid": fields[2] == "A"}
    return None


class GNSS:
    def __init__(self, i2c, addr=ADDR):
        self.i2c = i2c
        self.addr = addr
        self._buffer = b""
        self.quality = 0
        self.sats = 0
        self.lat = None
        self.lon = None
        self.hdop_x10 = None
        self.sentences = 0          # how many good sentences have arrived, to prove data flows
        self.bad = 0                # how many failed the checksum

    def _waiting(self):
        raw = self.i2c.readfrom_mem(self.addr, REG_BYTES_HI, 2)
        count = (raw[0] << 8) | raw[1]
        return 0 if count == 0xFFFF else count      # 0xFFFF means "nothing to read"

    def update(self):
        """Read everything that is waiting and process it. Call about once a second."""
        for _ in range(8):                           # at most 8 reads per call
            count = self._waiting()
            if count == 0:
                break
            self._buffer += bytes(self.i2c.readfrom_mem(self.addr, REG_STREAM, min(count, 250)))
        while b"\n" in self._buffer:
            line, _, self._buffer = self._buffer.partition(b"\n")
            self._handle(line.strip(b"\r\x00\xff ").decode("ascii", "ignore"))
        if len(self._buffer) > 1000:                 # junk with no line ends, throw it away
            self._buffer = b""

    def _handle(self, sentence):
        if not sentence.startswith("$"):
            return
        info = parse_sentence(sentence)
        if info is None:
            if "*" in sentence and not checksum_ok(sentence):
                self.bad += 1
            return
        self.sentences += 1
        if info["kind"] == "GGA":
            self.quality = info["quality"]
            self.sats = info["sats"]
            self.hdop_x10 = info.get("hdop_x10")
            if info["quality"] > 0 and info.get("lat") is not None:
                self.lat, self.lon = info["lat"], info["lon"]
            else:
                self.lat = self.lon = None

    def fix(self):
        """None until there is a position. Then (lat, lon, acc) as whole numbers."""
        if self.quality == 0 or self.lat is None or self.lon is None:
            return None
        hdop = self.hdop_x10 if self.hdop_x10 is not None else 99
        acc = max(1, (hdop * METERS_PER_HDOP + 9) // 10)
        return self.lat, self.lon, acc
