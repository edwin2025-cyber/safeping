"""Two helpers that set up the I2C bus and the SPI bus from pins.py.

On the board these use the chip's hardware I2C and SPI. If the hardware version
refuses the pins, they fall back to the slower "Soft" version, which works on any pin.
"""
from machine import I2C, SPI, Pin

import pins


def make_i2c(sda=None, scl=None):
    sda = pins.I2C_SDA if sda is None else sda
    scl = pins.I2C_SCL if scl is None else scl
    try:
        return I2C(0, sda=Pin(sda), scl=Pin(scl), freq=pins.I2C_FREQ)
    except Exception:
        from machine import SoftI2C
        return SoftI2C(sda=Pin(sda), scl=Pin(scl), freq=pins.I2C_FREQ)


def make_spi():
    try:
        return SPI(1, baudrate=1000000, polarity=0, phase=0,
                   sck=Pin(pins.SPI_SCK), mosi=Pin(pins.SPI_MOSI), miso=Pin(pins.SPI_MISO))
    except Exception:
        from machine import SoftSPI
        return SoftSPI(baudrate=1000000, polarity=0, phase=0,
                       sck=Pin(pins.SPI_SCK), mosi=Pin(pins.SPI_MOSI), miso=Pin(pins.SPI_MISO))
