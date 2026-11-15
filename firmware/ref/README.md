# Reference board firmware

A second SparkFun Thing Plus ESP32-C5 with a pressure sensor (BME280 on Qwiic), on USB wall power, on academic building floor 1, on school WiFi. It publishes the floor 1 air pressure every 30 s, so the server can take the weather out of each Fob's pressure. See `docs/message-format.md`, "Reference readings".

| File | What it is |
|---|---|
| `main.py` | The firmware. Copy it to the board as `/main.py`. |
| `config.example.py` | Copy to the board as `/config.py` and fill in. The real `config.py` is never committed. |

## Files on the board

Everything at the top level `/`, not `/lib`:

| Board path | From |
|---|---|
| `/main.py` | `firmware/ref/main.py` |
| `/config.py` | your filled-in copy of `firmware/ref/config.example.py` |
| `/msgsign.py` | `firmware/lib/msgsign.py` |
| `/ackcheck.py` | `firmware/lib/ackcheck.py` (msgsign.py uses its HMAC) |
| `/sendpath.py` | `firmware/lib/sendpath.py` |
| `/selfcheck.py` | `firmware/lib/selfcheck.py` |
| `/counterfile.py` | `firmware/lib/counterfile.py` |
| `/umqtt_safe.py` | `firmware/lib/umqtt_safe.py` |
| `/bme280.py` | `firmware/lib/bme280.py` |
| `/baro.py` | `firmware/lib/baro.py` |
| `/certs/broker-ca.pem` | the same CA file the Fob uses |

## What it does

- A reading every 2 s. Every 30 s one signed `REF` to `safeping/ref/<id>` (QoS 0) with the average pressure to one decimal, the temperature, the number of readings and the firmware version.
- Reconnects by itself when WiFi or the broker drops. The wait doubles after each failure, from 5 s up to 2 minutes.
- Watchdog on: a frozen program resets the board after 60 s.
- Counter: crash-safe like the Fob (`counter.txt` written through `counter.txt.tmp`), saved in blocks of 20 so the flash is written every 10 minutes, not every 30 s.

| Light | Meaning |
|---|---|
| Blue blink | WiFi not connected (joining, or waiting to try again) |
| Short green blink | A reading was published |
| Steady orange | The sensor is not reading, or the broker is not connected |
| Off | All good, between readings |

## Log lines (Thonny shell)

```
SafePing Reference REF-001 firmware ref-2026.11.15a
MicroPython 1.29.0
SENSOR model=BME280 chip_id=0x60 address=0x77 i2c=0x77
Sensor: BME280 (chip id 0x60) at 0x77
SELF_CHECK key=ok counter=ok pressure=ok wifi=ok reset=power_on fw=ref-2026.11.15a sensor=BME280@0x77
broker connected: ...
BOOT_SENT ctr=20 fail=0 sensor=BME280@0x77
REF_SENT ctr=21 p=98812.4 t=21.50 n=15 ts=1794754815
```

`SENSOR` says which chip it found, at which address, and every address that answered on the I2C bus. The same `sensor` goes in the board's signed BOOT report, which the Devices page shows as its Last start. `BMP280` also works (pressure and temperature, no humidity). If it says `off`, the sensor is a different part or is not plugged in.

## Test on the laptop

```
python tests/test_ref.py
```
