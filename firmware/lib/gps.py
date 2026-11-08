# Reads the text (NMEA) that the Adafruit Ultimate GPS FeatherWing sends and keeps the
# latest position. The wing's TX goes to the board's RX (IO12) and its RX to the board's
# TX (IO11). It talks at 9600 baud. Call update() often so the data never piles up.
# Positions are kept as whole microdegrees, the same units as the SafePing message format.

from machine import UART, Pin  # type: ignore
import time


class GPS:
    def __init__(self, uart_id=1, tx=11, rx=12, baud=9600):
        # If gps_check.py says "no data", try uart_id=0 here.
        self.uart = UART(uart_id, baudrate=baud, tx=Pin(tx), rx=Pin(rx), rxbuf=2048)
        self.buf = b""
        self.bytes_seen = 0     # bytes ever received. 0 means a wiring or pin problem.
        self.sentences = 0      # good sentences read
        self.bad = 0            # sentences thrown away (bad checksum)
        self.has_fix = False
        self.lat_e6 = None      # latitude in microdegrees, south is negative
        self.lon_e6 = None      # longitude in microdegrees, west is negative
        self.sats = 0
        self.hdop = ""          # lower is better. Under 2 is good.
        self.fix_ms = None      # when the last fix was read

    def update(self):
        """Read whatever has arrived and parse any full lines."""
        n = self.uart.any()
        if not n:
            return
        data = self.uart.read(n)
        if not data:
            return
        self.bytes_seen += len(data)
        self.buf += data
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            self._parse(line.strip())
        if len(self.buf) > 512:         # no line ending in a long time, so it is junk
            self.buf = b""

    def _parse(self, line):
        try:
            text = line.decode()
        except UnicodeError:
            self.bad += 1
            return
        if not text.startswith("$") or "*" not in text:
            self.bad += 1
            return
        body, _, given = text[1:].partition("*")
        check = 0
        for ch in body:
            check ^= ord(ch)
        try:
            ok = check == int(given[:2], 16)
        except ValueError:
            ok = False
        if not ok:
            self.bad += 1
            return
        self.sentences += 1
        parts = body.split(",")
        if parts[0][2:] == "GGA":       # GPGGA or GNGGA: the position sentence
            self._gga(parts)

    def _gga(self, p):
        # 0 id, 1 time, 2 lat, 3 N/S, 4 lon, 5 E/W, 6 quality (0 = no fix), 7 satellites, 8 hdop
        if len(p) < 9:
            return
        try:
            quality = int(p[6]) if p[6] else 0
            self.sats = int(p[7]) if p[7] else 0
        except ValueError:
            return
        self.hdop = p[8]
        if quality == 0 or not p[2] or not p[4]:
            self.has_fix = False
            return
        lat = self._micro(p[2], 2)
        lon = self._micro(p[4], 3)
        if lat is None or lon is None:
            return
        self.lat_e6 = -lat if p[3] == "S" else lat
        self.lon_e6 = -lon if p[5] == "W" else lon
        self.has_fix = True
        self.fix_ms = time.ticks_ms()

    @staticmethod
    def _micro(text, deg_digits):
        """Turn NMEA 'ddmm.mmmm' into microdegrees using whole numbers only."""
        try:
            degrees = int(text[:deg_digits])
            whole, _, frac = text[deg_digits:].partition(".")
            frac = (frac + "00000")[:5]
            minutes_e5 = int(whole) * 100000 + int(frac)
        except ValueError:
            return None
        return degrees * 1000000 + minutes_e5 // 6

    @staticmethod
    def text(e6):
        """Microdegrees to text, like -86.655566."""
        sign = "-" if e6 < 0 else ""
        e6 = abs(e6)
        return "{}{}.{:06d}".format(sign, e6 // 1000000, e6 % 1000000)

    def lat_text(self):
        return self.text(self.lat_e6)

    def lon_text(self):
        return self.text(self.lon_e6)

    def age_s(self):
        if self.fix_ms is None:
            return None
        return time.ticks_diff(time.ticks_ms(), self.fix_ms) // 1000

    def position(self, max_age_s=10):
        """(lat_text, lon_text) if there is a recent fix, otherwise None."""
        age = self.age_s()
        if not self.has_fix or age is None or age > max_age_s:
            return None
        return self.lat_text(), self.lon_text()
