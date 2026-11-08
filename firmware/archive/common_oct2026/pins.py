"""SafePing pin plan for the SparkFun Thing Plus ESP32-C5.

ONE place for every pin number. The bring-up scripts and the drivers read from here.
The Fob, the Relay and the Reference all use the same board, so they share this file.
Copy it to the board together with the driver files.

Each line says how sure we are:
  FROM SCHEMATIC  read from SparkFun's schematic. Fixed on the board, you cannot move it.
  PROPOSED        our choice from the free header pins. Confirm with bringup/00_pin_walk.py
                  and the silkscreen on the board, then change it here if needed.

If you change a number here, change docs/hardware-connections.md to match.
"""

# ---- I2C (the Qwiic connector and the header SDA/SCL pins are the same bus) ----
# Carries: BME280 pressure sensor (0x77 or 0x76), SAM-M10Q GPS (0x42), and the
# battery fuel gauge that is already on the board (0x36).
I2C_SDA = 23          # FROM SCHEMATIC (net IO23/SDA)
I2C_SCL = 24          # FROM SCHEMATIC (net IO24/SCL)
# SparkFun's web page says the Qwiic bus is on IO6 and IO7, which disagrees with the
# schematic (that page looks copied from another board). bringup/01_i2c_scan.py tries
# both pairs and tells you which one is real.
I2C_ALT = (6, 7)
I2C_FREQ = 100000     # Qwiic default speed. Slow and safe.

# ---- SPI (LoRa radio) ----
SPI_SCK = 10          # FROM SCHEMATIC (net IO10/SCK)
SPI_MISO = 9          # FROM SCHEMATIC (net IO9/POCI, "POCI" is the new name for MISO)
SPI_MOSI = 8          # FROM SCHEMATIC (net IO8/PICO, "PICO" is the new name for MOSI)
# These three are shared with the microSD slot on the board. That is fine while no card
# is inserted, so leave the slot empty.
LORA_CS = 4           # PROPOSED (a free header pin)
LORA_RST = 5          # PROPOSED
LORA_IRQ = 0          # PROPOSED (the radio's G0 pin, "packet done" signal). No driver reads it yet.
# Not GPIO 6: that is half of the backup I2C pair (see I2C_ALT above).

# ---- Fob only ----
BUTTON = 1            # PROPOSED. One leg to this pin, the other leg to GND.
NEOPIXEL = 2          # PROPOSED. Data In of the NeoPixel Mini PCB.
MOTOR = 3             # PROPOSED. Through a 1 k resistor to the base of the PN2222.

# ---- Do not use these for outside wiring ----
# IO27 drives the RGB LED that is already on the board, and IO27 and IO28 (the BOOT
# button) are read at reset to choose the boot mode. IO11 and IO12 are the TX and RX
# header pins (UART0). IO13 and IO14 are the USB connection. IO25 is the microSD CS.
RESERVED = (11, 12, 13, 14, 25, 27, 28)

# Pins we expect to sit on the A0 to A5 header holes (the schematic calls them IOA1 to
# IOA6). Used by 00_pin_walk.py. Confirm against the silkscreen.
CANDIDATE_FREE_PINS = (0, 1, 2, 3, 4, 5, 6)
