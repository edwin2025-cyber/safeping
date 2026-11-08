# Bring-up scripts

Short scripts you run on the board the day the parts arrive. Each one tests one part and prints what "good" looks like. They are written so that if something fails, you know which part and which wire.

Read `../../docs/hardware-connections.md` first. It says what connects where.

## Run them in this order

| Script | Proves | Needs |
|---|---|---|
| `00_pin_walk.py` | Which header hole is which GPIO | Only an LED and a resistor |
| `01_i2c_scan.py` | The I2C bus works and which parts answer | The Qwiic parts |
| `02_battery.py` | The battery gauge and the charger | The LiPo battery |
| `03_bme280.py` | Pressure and temperature, and that pressure follows height | The BME280 |
| `04_gps.py` | The GPS sends data, then gets a position | The GPS, and sky |
| `05_button_led_motor.py` | Button, NeoPixel and motor | The Fob wiring |
| `06_lora.py` | The LoRa radio (one board, then two) | The radio and its antenna |

## Put the files on the board

The board comes with MicroPython installed. You need the shared files from `firmware/common` on the board, plus the one script you want to run.

**With Thonny (easiest):** open each file, choose File, Save as, pick "MicroPython device", and keep the same file name. Do this once for `pins.py`, `hw.py`, `max17048.py`, `bme280.py`, `gnss.py` and `sx127x.py`. Then open a bring-up script and press Run.

**With mpremote** (`pip install mpremote`), from the `firmware` folder. Replace COM5 with your board's port:

```
mpremote connect COM5 fs cp common/pins.py common/hw.py common/max17048.py common/bme280.py common/gnss.py common/sx127x.py :
mpremote connect COM5 run bringup/01_i2c_scan.py
```

Do not copy `test_drivers.py` or `test_scripts.py` to the board. They are for your laptop.

## Test them on your laptop first

No hardware needed. These run the code against fake parts:

```
cd firmware/common
python test_drivers.py
cd ../bringup
python test_scripts.py
```

Expected last lines: `42 passed, 0 failed` and `26 passed, 0 failed`.

If the pynmea2 library is not installed, the first one says `40 passed, 0 failed` and prints a line that starts with `skip`. That is fine. Run `pip install pynmea2` and run it again to get 42.

## When something fails

| What you see | Most likely cause |
|---|---|
| `01_i2c_scan.py` sees only 0x36 | The Qwiic cable is not seated, or it is in the wrong port |
| `01_i2c_scan.py` finds the bus on a different pair | Change `I2C_SDA` and `I2C_SCL` in `pins.py` |
| `04_gps.py`: `sentences` stays at 0 | GPS not on the bus (run the scan, look for 0x42) |
| `04_gps.py`: sentences rise but no fix | No sky view. Go to a window or outside and wait a few minutes |
| `06_lora.py`: version register is not 0x12 | SPI wiring, or the CS pin. Check SCK, MISO, MOSI, CS |
| `05`: NeoPixel dim or flickers | Move its power wire from 3V3 to the battery pin |
| `05`: motor buzzes at power on | Transistor or resistor is wrong. Unplug it |
