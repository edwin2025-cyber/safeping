# Hardware connections: what connects where

This is the wiring guide for the Fob, the Relay and the Reference. All three use the same board, the SparkFun Thing Plus ESP32-C5. Every pin number below lives in one file, `firmware/common/pins.py`. If a number changes, change it there and change it here.

Read the **status** column. Some pins are fixed by the board and read from SparkFun's schematic. Others are our own choice and must be confirmed on the real board.

## 1. The big picture

| Part | How it connects | Needs soldering | What it gives us | Test script |
|---|---|---|---|---|
| Battery gauge (MAX17048) | Already on the board, on the I2C bus | no | Battery percent for the `bat` field | `02_battery.py` |
| BME280 pressure sensor | Qwiic cable to the board's Qwiic port | no | Pressure `p` and temperature `t` | `03_bme280.py` |
| SAM-M10Q GPS | Qwiic cable, chained after the BME280 | no | `lat`, `lon`, `acc` | `04_gps.py` |
| RFM95W LoRa radio | SPI (3 wires) plus 3 control wires | yes | The LoRa fallback and the Relay link | `06_lora.py` |
| Push button | 1 wire to a pin, 1 wire to GND | yes | The 4 alert patterns | `05_button_led_motor.py` |
| NeoPixel Mini PCB | 3 wires (power, ground, data) | yes | The status LED | `05_button_led_motor.py` |
| Vibration motor | A pin, a resistor, a transistor, a diode | yes | The buzz patterns | `05_button_led_motor.py` |
| LiPo battery | JST connector on the board | no | Portable power | `02_battery.py` |

The Qwiic bus carries three things at once, each at its own address:

| Address | Part |
|---|---|
| `0x36` | Battery gauge, on the board |
| `0x42` | GPS |
| `0x77` (or `0x76`) | BME280 |

The **Reference** needs only the BME280 on Qwiic and USB power. The **Relay** needs only the LoRa radio and USB power. The **Fob** needs everything.

## 2. Pin table

| Function | GPIO | Where on the board | Status |
|---|---|---|---|
| I2C data (SDA) | 23 | Qwiic port, and the header hole labeled SDA | From schematic |
| I2C clock (SCL) | 24 | Qwiic port, and the header hole labeled SCL | From schematic |
| SPI clock (SCK) | 10 | Header hole SCK | From schematic |
| SPI data in (MISO, labeled POCI) | 9 | Header hole POCI | From schematic |
| SPI data out (MOSI, labeled PICO) | 8 | Header hole PICO | From schematic |
| LoRa chip select (CS) | 26 | A free header hole | Confirmed 2026-11-08 |
| LoRa reset (RST) | 6 | A free header hole | Confirmed 2026-11-08 |
| LoRa interrupt (G0) | not wired | | The driver polls |
| Button | 1 | A free header hole, other side to GND (internal pull-up) | Confirmed 2026-11-08 |
| Status LED (onboard NeoPixel) | 27 | On the board | Confirmed 2026-11-08 |
| Motor transistor | 3 | A free header hole | Confirmed 2026-11-08 |
| GPS wing TX (into the board) | 12 | UART1 RX | Confirmed 2026-11-08 |
| GPS wing RX (from the board) | 11 | UART1 TX | Confirmed 2026-11-08 |

**Do not use** GPIO 27 or 28. The board's own RGB LED is on 27, and 27 and 28 (the BOOT button) are read at reset to choose the boot mode. Also avoid 11 and 12 (the TX and RX holes), 13 and 14 (USB) and 25 (microSD).

### Three things we do not know yet

1. **The I2C pins.** SparkFun's schematic says GPIO 23 and 24. SparkFun's web page says GPIO 6 and 7. The page looks copied from another board. `01_i2c_scan.py` tries both and tells you which one is real. If it is the other pair, change `I2C_SDA` and `I2C_SCL` in `pins.py`.
2. **Which header hole is which free GPIO.** The schematic names six analog pins IOA1 to IOA6, which should be A0 to A5 in order, but we could not confirm that from the files we could read. Run `00_pin_walk.py` with an LED to find out, then fill in the table in section 7.
3. **The NeoPixel power voltage.** See the NeoPixel notes below.

## 3. Wiring each part

Always wire with the USB unplugged and the battery unplugged. Add one part at a time and test it before adding the next.

### 3.1 Qwiic parts (BME280 and GPS). No soldering.
1. Plug a Qwiic cable from the Thing Plus Qwiic port to either Qwiic port on the BME280.
2. Plug a second Qwiic cable from the other Qwiic port on the BME280 to either port on the GPS.
3. The plugs only fit one way. Do not force them.
4. Run `01_i2c_scan.py`. You should see 0x36, 0x42 and 0x77.

The GPS has a chip antenna and needs to see the sky. Test it at a window or outside.

### 3.2 LoRa radio (RFM95W). Solder headers first.

| Radio pin | Goes to |
|---|---|
| VIN | 3V3, by a direct jumper from the board (not through a breadboard rail) |
| GND | GND, by a direct jumper the same way |
| SCK | GPIO 10 (SCK) |
| MISO | GPIO 9 (POCI) |
| MOSI | GPIO 8 (PICO) |
| CS | GPIO 26 |
| RST | GPIO 6 |
| G0 | not wired (the driver polls) |
| EN | leave it unconnected (it is held high by the board) |

- Put a 100 uF electrolytic capacitor across VIN and GND at the breakout (stripe to GND).
- **Fit the antenna before you power it on.** Sending with no antenna can damage the radio. If your antenna is a plain wire, cut it to about 78 mm. That is a quarter wavelength at 915 MHz.
- The radio is shared with the board's microSD slot on the SPI wires. Leave the slot empty.
- Run `06_lora.py` with `ROLE = "check"` first. It must print `version register = 0x12`.

### 3.3 Button
- One leg to GPIO 1, the other leg to GND. No resistor, because the code turns on the pin's internal pull-up.
- **Check the NeoPixel part before you trust it as the button.** The Adafruit "NeoPixel Mini Button PCB" is an LED board shaped like a button. The product page lists no switch, and the same product is also sold as "NeoPixel Mini PCB". Look at the product photos. If there is no switch, the BOM needs a separate push button, such as a 6 mm tactile switch (about $1 to $3), and the printed button cap sits over it.
- Until a switch arrives, touching a wire from GPIO 1 to GND does the same thing.

### 3.4 NeoPixel Mini PCB
1. Solder three wires to one set of pads on the back. The page does not name the pads. Read the tiny labels on the board and use the **input** set: power (V or 5V), ground (G), and data in (IN or DI). Leave the output set empty.
2. Wire it: power to 3V3, ground to GND, data in to GPIO 2.
3. Keep the brightness low in code. A NeoPixel is very bright up close.

**Power voltage.** The page says the part is a 5 V part that "can run as low as 3.5 V but color will be dimmed". The board's 3V3 pin is below that, so the colors may be dim or wrong. Do not use 5 V, because then the 3.3 V data signal is too weak to be read. Try 3V3 first. If the colors are dim or flicker, move the power wire to the board's battery pin (3.5 to 4.2 V) and test again. Record what works.

### 3.5 Vibration motor. Never wire the motor straight to a pin.
A pin can only supply a few milliamps. The motor needs about 70 to 100 mA, so the pin switches a transistor, and the transistor switches the motor.

```
GPIO 3 ---[ 1 kΩ ]--- base (B) of the PN2222
                       base (B) ---[ 10 kΩ ]--- GND
                       emitter (E) --- GND
                       collector (C) --- motor wire 1
3V3 -------------------------------- motor wire 2
1N4001 across the motor: stripe end to 3V3, plain end to the collector
```

- **PN2222 pins.** In the usual TO-92 package, with the flat face toward you and the legs pointing down, the order from left to right is Emitter, Base, Collector. Confirm that on the datasheet for your part before you power it on.
- **Diode direction.** The stripe (the cathode) goes to the 3V3 side. It absorbs the spike when the motor switches off.
- **Resistor.** The BOM has no resistor line. Any value from 330 Ω to 2.2 kΩ works for the base. Get a small assortment. A 10 kΩ from base to GND is a good extra, so the motor stays off while the board starts up.
- **The motor never goes on the pin.** If it buzzes at power on, the diode or resistor is wrong. Unplug it.

### 3.6 Battery
- The battery is a 3.7 V 420 mAh LiPo.
- Plug the LiPo into the JST connector on the board.
- **Check the polarity first.** Different brands wire JST connectors in opposite directions, and the wrong way can destroy the board. Match the board's + and - markings against the red and black wires. If the battery you own does not match, swap the wires in the connector, or buy a matching one.
- The board charges the battery from USB. The yellow CHG light is on while it charges.

## 4. Power-up order

1. Board alone on USB. Open the console. Make sure the board answers.
2. Copy the files in `firmware/common` and `firmware/bringup` to the board (see `firmware/bringup/README.md`).
3. Qwiic parts: `01_i2c_scan.py`, then `03_bme280.py`, then `04_gps.py`.
4. Battery: `02_battery.py`.
5. Button, NeoPixel, motor: `05_button_led_motor.py`.
6. LoRa radio: `06_lora.py`, check first, then two boards.
7. Only after all of those pass, wire the parts into `main.py` (`read_gps`, `read_sensors`, `lora_send`).

## 5. How we know we are getting data

A part is "working" when its script shows the numbers below. Write the date and result in the last column.

| Part | Good looks like | Date and result |
|---|---|---|
| Battery gauge | version `0x0010` to `0x001F`, 3300 to 4200 mV, 0 to 100 % | |
| BME280 | chip id `0x60`, about 98000 to 102000 Pa, room temperature, and about 20 to 25 Pa lower when lifted 2 m | |
| GPS data flow | `sentences` goes up every second, `bad` stays near 0 | |
| GPS position | after sky view, a `FIX` line within about 10 m of where you stand | |
| Button | `PRESSED` and `RELEASED after N ms` on every press, and `SILENT HOLD` at 5 s | |
| NeoPixel | red, green, blue, white in that order, not dim | |
| Motor | buzzes while the button is held, silent otherwise, and silent at power on | |
| LoRa | `version register = 0x12`, then `received ...` with a signal strength on the second board | |

## 6. Gotchas

- **3.3 V only.** The ESP32-C5 pins are not 5 V tolerant. Never connect a 5 V signal to a pin.
- **LoRa message size.** One LoRa packet holds 255 bytes. A full alert is about 210 to 235 bytes. Keep device IDs short (the example `FOB-001` is fine). When we connect LoRa to `main.py`, switch to compact JSON (no spaces) to save about 25 bytes.
- **Two I2C parts of the same kind** on one bus would clash. We have one BME280 per board, so this is fine.
- **GPS needs sky.** The GPS data flow can be proven at a desk. A position fix needs a window or the outdoors.
- **First reading of the battery gauge** can be off for a few seconds after power-up.
- **Flash the board's MicroPython** only if it stops answering. It ships with MicroPython installed.

## 7. Pin walk results (fill in on the day)

Run `00_pin_walk.py` with only an LED connected. For each GPIO, write the label printed next to the hole that lit up.

| GPIO | Label next to the hole |
|---|---|
| 0 | |
| 1 | |
| 2 | |
| 3 | |
| 4 | |
| 5 | |
| 6 | |

## 8. What has and has not been tested

- **Tested on a laptop:** the battery, pressure, GPS and radio driver code, against known-good values (Bosch's own worked example for the pressure math, the pynmea2 library for GPS when it is installed, and a software model of the radio chip). The bring-up scripts run against fake parts.
- **Also run once on MicroPython 1.29** (a WebAssembly build on a laptop, not the board): all 14 board-side files compile, and the pressure, GPS and battery math gave the expected numbers. The radio driver was only compiled there. That run is not in this repo.
- **Not tested:** any real part. The pin choices marked Proposed, the I2C pair, the NeoPixel voltage, the LoRa radio driver on the real chip, and the motor circuit are all unconfirmed until the parts arrive.
- **Sources:** SparkFun Thing Plus ESP32-C5 schematic, SparkFun hookup guide, Adafruit RFM95W and NeoPixel Mini PCB product pages, SparkFun SAM-M10Q hookup guide.

## Bench wiring confirmed 2026-11-08

- I2C is SDA 23, SCL 24 (`I2C(0)`): battery gauge MAX17048 at 0x36 on the board, BME280 at 0x77 on the Qwiic port.
- GPS: Adafruit Ultimate GPS FeatherWing on UART1, wing TX to IO12, wing RX to IO11, 9600 baud.
