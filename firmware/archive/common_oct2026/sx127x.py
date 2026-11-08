"""Small driver for the RFM95W LoRa radio (a Semtech SX1276 chip) over SPI.

The Fob sends an alert as a LoRa packet when WiFi is not available. The Relay listens
and republishes it to MQTT. Both use this file.

It does only what SafePing needs: send one packet, receive one packet, report the
signal strength. Settings are the common starting point for 915 MHz in the US:
915 MHz, bandwidth 125 kHz, spreading factor 7, coding rate 4/5, CRC on, 17 dBm.

IMPORTANT
  * Fit the antenna BEFORE you transmit. Sending with no antenna can damage the radio.
  * A LoRa packet holds at most 255 bytes. A full alert is about 210 to 235 bytes, so
    keep device IDs short.
  * Written from the SX1276 datasheet and tested against a software model of the chip.
    It has NOT yet run on the real radio. The first real test is bringup/06_lora.py,
    which reads the chip's version register (it must say 0x12) before anything else.

Usage:
    radio = SX127x(spi, cs_pin, reset_pin)
    radio.begin()
    radio.send(b"hello")
    packet = radio.receive(timeout_ms=5000)     # None, or (data, rssi_dbm, snr_db)
"""
import time

# registers
REG_FIFO = 0x00
REG_OP_MODE = 0x01
REG_FRF_MSB = 0x06
REG_PA_CONFIG = 0x09
REG_LNA = 0x0C
REG_FIFO_ADDR_PTR = 0x0D
REG_FIFO_TX_BASE = 0x0E
REG_FIFO_RX_BASE = 0x0F
REG_FIFO_RX_CURRENT = 0x10
REG_IRQ_FLAGS = 0x12
REG_RX_NB_BYTES = 0x13
REG_PKT_SNR = 0x19
REG_PKT_RSSI = 0x1A
REG_MODEM_CONFIG_1 = 0x1D
REG_MODEM_CONFIG_2 = 0x1E
REG_PREAMBLE_MSB = 0x20
REG_PAYLOAD_LENGTH = 0x22
REG_MODEM_CONFIG_3 = 0x26
REG_SYNC_WORD = 0x39
REG_VERSION = 0x42
REG_PA_DAC = 0x4D

# operating modes (low 3 bits of REG_OP_MODE). Bit 7 selects LoRa instead of FSK.
LONG_RANGE = 0x80
MODE_SLEEP = 0x00
MODE_STANDBY = 0x01
MODE_TX = 0x03
MODE_RX_CONTINUOUS = 0x05

# flags in REG_IRQ_FLAGS
IRQ_TX_DONE = 0x08
IRQ_CRC_ERROR = 0x20
IRQ_RX_DONE = 0x40

EXPECTED_VERSION = 0x12
MAX_PACKET = 255

BANDWIDTH_CODES = {7800: 0, 10400: 1, 15600: 2, 20800: 3, 31250: 4, 41700: 5,
                   62500: 6, 125000: 7, 250000: 8, 500000: 9}


class SX127x:
    def __init__(self, spi, cs, reset, frequency_hz=915000000, bandwidth_hz=125000,
                 spreading_factor=7, coding_rate=5, tx_power_dbm=17, sync_word=0x12):
        self.spi = spi
        self.cs = cs
        self.reset_pin = reset
        self.frequency_hz = frequency_hz
        self.bandwidth_hz = bandwidth_hz
        self.sf = spreading_factor
        self.cr = coding_rate
        self.tx_power_dbm = tx_power_dbm
        self.sync_word = sync_word

    # ---- low level ----
    def _transfer(self, out):
        back = bytearray(len(out))
        self.cs.value(0)
        try:
            self.spi.write_readinto(out, back)
        finally:
            self.cs.value(1)
        return back

    def read_reg(self, address):
        return self._transfer(bytes([address & 0x7F, 0]))[1]

    def write_reg(self, address, value):
        self._transfer(bytes([address | 0x80, value & 0xFF]))

    def _read_fifo(self, count):
        return bytes(self._transfer(bytes([REG_FIFO & 0x7F]) + bytes(count))[1:])

    def _write_fifo(self, data):
        self._transfer(bytes([REG_FIFO | 0x80]) + bytes(data))

    # ---- set up ----
    def reset(self):
        """Pulse the reset pin low, then let the chip start up (SX1276 datasheet 7.2.2)."""
        self.reset_pin.value(0)
        time.sleep_ms(2)
        self.reset_pin.value(1)
        time.sleep_ms(10)

    def version(self):
        return self.read_reg(REG_VERSION)

    def begin(self):
        """Reset the chip and apply the settings. Raises OSError if the radio does not
        answer, which almost always means a wiring problem."""
        self.cs.value(1)
        self.reset()
        version = self.version()
        if version != EXPECTED_VERSION:
            raise OSError("LoRa radio not found (version register read 0x{:02x}, "
                          "expected 0x12). Check wiring.".format(version))
        self.write_reg(REG_OP_MODE, LONG_RANGE | MODE_SLEEP)    # only sleep allows the switch to LoRa
        time.sleep_ms(10)
        self.write_reg(REG_OP_MODE, LONG_RANGE | MODE_STANDBY)
        # carrier frequency: Frf = frequency * 2^19 / 32 MHz
        frf = (self.frequency_hz << 19) // 32000000
        self.write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
        self.write_reg(REG_FRF_MSB + 1, (frf >> 8) & 0xFF)
        self.write_reg(REG_FRF_MSB + 2, frf & 0xFF)
        self.write_reg(REG_FIFO_TX_BASE, 0x00)
        self.write_reg(REG_FIFO_RX_BASE, 0x00)
        self.write_reg(REG_LNA, 0x23)                           # maximum receive gain, boost on
        self._set_modem()
        self._set_power()
        self.write_reg(REG_SYNC_WORD, self.sync_word)
        self.write_reg(REG_PREAMBLE_MSB, 0x00)
        self.write_reg(REG_PREAMBLE_MSB + 1, 0x08)              # 8 preamble symbols
        return version

    def _set_modem(self):
        bw = BANDWIDTH_CODES[self.bandwidth_hz]
        # bandwidth, coding rate (5 means 4/5 so the code is cr - 4), explicit header
        self.write_reg(REG_MODEM_CONFIG_1, (bw << 4) | ((self.cr - 4) << 1))
        # spreading factor, CRC on
        self.write_reg(REG_MODEM_CONFIG_2, (self.sf << 4) | 0x04)
        # low data rate optimize is needed when one symbol lasts 16 ms or more
        symbol_ms = (1 << self.sf) * 1000 // self.bandwidth_hz
        self.write_reg(REG_MODEM_CONFIG_3, 0x04 | (0x08 if symbol_ms >= 16 else 0))

    def _set_power(self):
        # The RFM95W wires its antenna to the PA_BOOST pin: output = 17 - (15 - code) dBm.
        power = max(2, min(17, self.tx_power_dbm))
        self.write_reg(REG_PA_DAC, 0x84)                        # normal power (not the +20 dBm mode)
        self.write_reg(REG_PA_CONFIG, 0x80 | (power - 2))

    # ---- send ----
    def send(self, data, timeout_ms=5000):
        """Send one packet and wait until it has left the antenna. Returns True on success."""
        if len(data) > MAX_PACKET:
            raise ValueError("packet is {} bytes, the limit is 255".format(len(data)))
        self.write_reg(REG_OP_MODE, LONG_RANGE | MODE_STANDBY)
        self.write_reg(REG_FIFO_ADDR_PTR, 0x00)
        self._write_fifo(data)
        self.write_reg(REG_PAYLOAD_LENGTH, len(data))
        self.write_reg(REG_IRQ_FLAGS, 0xFF)
        self.write_reg(REG_OP_MODE, LONG_RANGE | MODE_TX)
        waited = 0
        while not (self.read_reg(REG_IRQ_FLAGS) & IRQ_TX_DONE):
            time.sleep_ms(2)
            waited += 2
            if waited > timeout_ms:
                self.write_reg(REG_OP_MODE, LONG_RANGE | MODE_STANDBY)
                return False
        self.write_reg(REG_IRQ_FLAGS, 0xFF)
        self.write_reg(REG_OP_MODE, LONG_RANGE | MODE_STANDBY)
        return True

    # ---- receive ----
    def receive(self, timeout_ms=5000):
        """Listen for one packet. Returns (data, rssi_dbm, snr_db), or None if nothing
        good arrived in time. Packets with a bad CRC are skipped."""
        self.write_reg(REG_IRQ_FLAGS, 0xFF)
        self.write_reg(REG_FIFO_ADDR_PTR, 0x00)
        self.write_reg(REG_OP_MODE, LONG_RANGE | MODE_RX_CONTINUOUS)
        waited = 0
        try:
            while waited <= timeout_ms:
                flags = self.read_reg(REG_IRQ_FLAGS)
                if flags & IRQ_RX_DONE:
                    self.write_reg(REG_IRQ_FLAGS, 0xFF)
                    if flags & IRQ_CRC_ERROR:
                        waited += 2
                        continue                                  # corrupted, keep listening
                    count = self.read_reg(REG_RX_NB_BYTES)
                    self.write_reg(REG_FIFO_ADDR_PTR, self.read_reg(REG_FIFO_RX_CURRENT))
                    data = self._read_fifo(count)
                    snr = self.read_reg(REG_PKT_SNR)
                    snr = (snr - 256 if snr > 127 else snr) / 4
                    rssi = self.read_reg(REG_PKT_RSSI) - 157      # 915 MHz is the high-frequency port
                    return data, rssi, snr
                time.sleep_ms(2)
                waited += 2
            return None
        finally:
            self.write_reg(REG_OP_MODE, LONG_RANGE | MODE_STANDBY)

    def sleep(self):
        self.write_reg(REG_OP_MODE, LONG_RANGE | MODE_SLEEP)
