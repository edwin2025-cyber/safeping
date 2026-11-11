# How to run SafePing

Quick steps for every part of the project. Run everything from VS Code's terminal: press **Ctrl+`** in the `safeping` folder.

Notes for this laptop:
- Use `npm.cmd`, not `npm`. PowerShell blocks `npm.ps1`.
- To use more than one program at a time, open another terminal with the **+** button.
- Ctrl+C stops whatever is running in a terminal.
- Keys and passwords live in `Documents\safeping-private`. Never paste them into chat, a screenshot or a commit.

---

## 1. Dashboard

### Fake data, no server (design work)
```
cd dashboard
npm.cmd run dev:mock
```
Open http://localhost:5173. The page updates as you edit the code.

For CARTO map tiles in mock mode, `dashboard\.env.mock.local` must hold `VITE_CARTO_KEY=...`. Git ignores that file.

### Real data
```
cd server
$env:NO_MQTT = "1"
$env:PA_PER_FLOOR = "55"
$env:CARTO_KEY = (Get-Content "$HOME\Documents\safeping-private\carto_key.txt").Trim()
python app.py
```
Open http://127.0.0.1:5000.

This serves the last **built** dashboard. If you changed dashboard code, rebuild first:
```
cd dashboard
npm.cmd run build
```

### Real data with live editing
1. Terminal 1: the server, as above.
2. Terminal 2:
   ```
   cd dashboard
   npm.cmd run dev
   ```
3. Open http://localhost:5173.

### Checks after dashboard changes
```
cd dashboard
npm.cmd run contrast
npm.cmd run build
```

---

## 2. Real alerts from the Relay (LoRa over USB)

The server must already be running (section 1, real data).

New terminal:
```
cd server
python serial_bridge.py
```
Add `--echo` to see everything the Relay prints.

Only one program can use COM14 at a time. Close Thonny on the Relay first. Do not run the bridge and the field logger together.

---

## 3. Field tests (logger)

Plug the Relay into COM14. For tests that log the Fob too, plug it into COM15. Start the logger **before** opening Thonny.

### Relay only (Fob on its battery, out in the field)
```
python tests\field_log.py --label NAME --no-fob
```

### Relay and Fob (both on USB, at the desk)
```
python tests\field_log.py --label NAME
```

- Replace `NAME` with something short, like `dt10_run2` or `failover_pre_t1`.
- Ctrl+C stops it and prints the summary.
- Each run gets its own folder in `logs\<date>\`.
- `python tests\field_log.py --help` lists every option.

---

## 4. Server tests and tools

All from the `server` folder:
```
cd server
```

| What | Command |
|---|---|
| Security test (must say 16 of 16) | `python test_attacks.py` |
| Register a device | `python add_device.py FOB-001 "Student name" --key <key from safeping-private>` |
| Send a fake alert | `python fake_fob.py --direct` (see `--help` for options) |

### Start fresh before formal tests (archive the database)
1. Stop the server.
2. Move the old database out of the way:
   ```
   Move-Item server\safeping.db* ..\safeping-private\archive\
   ```
3. Start the server. It makes a new empty database.
4. Register the devices again with `add_device.py` and their saved keys.

---

## 5. The boards (Thonny)

- **Fob:** COM15. **Relay:** COM14.
- **To stop a running program:** click in the Shell and press **Ctrl+C**. Do not use the Stop button, which causes write timeouts.
- **To run a script from the laptop without saving it to the board:** open it in Thonny (File > Open > This computer) and press **F5**.
- **To edit the board's settings:** View > Files, then double-click `config.py` under "MicroPython device". Save with Ctrl+S.
- **After changing `config.py`:** press the board's **RST** button. Unplugging USB does not reset it while the LiPo is attached.
- **WiFi check (Fob):** open `tests\wifi_check.py` and press F5.
- **LoRa only on the Fob:** set `WIFI_SSID = "none"` in its `config.py`.

Battery rules:
- Only charge the LiPo while you are awake.
- Unplug the LiPo from the board whenever you leave the board alone.

---

## 6. Phone pages (range-logger on GitHub Pages)

- **Floor walk:** `floor.html`
- **DT-10 GPS test:** `dt10.html`

Before each test, tap **Clear all** twice. After each test, tap **Export CSV** and put the file in that test's `logs\` run folder.

---

## 7. Committing

```
git status
```
**Make sure none of these appear:** `.env` files, `.db` files, `carto_key.txt`, any `config.py` from `firmware\` or `tests\`.

Then:
```
git add -A
git commit -m "Short description of what changed"
git push
```
No Co-Authored-By lines.

---

## 8. Cloud broker (EMQX Cloud Serverless)

The Fob sends over WiFi to the cloud broker first, then LoRa. The server reads the broker and sends each Fob a signed ack once its alert is saved. TLS only, port 8883.

Logins:
- `safeping-fob`: used by the Fobs
- `safeping-server`: used by the server and `tests\broker_check.py`

The real address, passwords and CA file live in `safeping-private`. The values below are placeholders.

### Server settings (environment variables)
```
$env:SAFEPING_MQTT_HOST = "your-deployment-address"
$env:SAFEPING_MQTT_PORT = "8883"
$env:SAFEPING_MQTT_USER = "safeping-server"
$env:SAFEPING_MQTT_PASS = "the-server-broker-password"
$env:SAFEPING_MQTT_CA   = "$HOME\Documents\safeping-private\the-ca-file.crt"
```
- `SAFEPING_MQTT_PORT` is optional. It defaults to 8883 when a CA file is set.
- With `SAFEPING_MQTT_CA` set, the server uses TLS and checks the certificate.
- The old names `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS` still work if the new ones are not set (the local Mosquitto setup).

Check the broker first:
```
python tests\broker_check.py
```

### Start the server with MQTT on
Same terminal as the settings above. Do **not** set `NO_MQTT`:
```
cd server
Remove-Item Env:NO_MQTT -ErrorAction SilentlyContinue
$env:PA_PER_FLOOR = "55"
$env:CARTO_KEY = (Get-Content "$HOME\Documents\safeping-private\carto_key.txt").Trim()
python app.py
```
You should see `[mqtt] connected to ...:8883 with TLS`. For each Fob alert:
- `[mqtt] ack sent to safeping/ack/FOB-001 ctr 212`
- `[mqtt] safeping/alert/FOB-001 -> {...}`

The ack line comes first, because the ack goes out as soon as the alert is saved.

To run only the listener (no dashboard): `python mqtt_listener.py`.

### The Fob's `config.py`
Add these lines. Use the real values from `safeping-private`:
```
WIFI_SSID = "the-wifi-name"
WIFI_PASSWORD = "the-wifi-password"
MQTT_HOST = "your-deployment-address"
MQTT_PORT = 8883
MQTT_USER = "safeping-fob"
MQTT_PASSWORD = "the-fob-broker-password"
MQTT_TLS = True
MQTT_CA_FILE = "/certs/broker-ca.pem"
WIFI_BUDGET_MS = 5000
WIFI_JOIN_MS = 3000
MQTT_ACK_WAIT_MS = 2000
WATCHDOG_ENABLED = False
STATUS_SUCCESS_PATTERN = "ok"
```
- `WIFI_TIMEOUT_MS`, `SEND_ATTEMPTS` and `MQTT_PASS` are old names. You can delete them. `MQTT_PASS` still works if `MQTT_PASSWORD` is missing.
- `WIFI_SSID = "none"` still means LoRa only.

### The CA file on the Fob
1. In Thonny: View > Files. Under "MicroPython device", right-click and make a new folder called `certs` (at the top level, so the path is `/certs`).
2. On "This computer", find the CA file in `safeping-private`. Right-click it > Upload to `/certs`.
3. On the board, rename it to `broker-ca.pem`.
4. Press RST. The boot lines must **not** say `TLS CA file missing`.

The Fob reads the CA as PEM. If the board refuses PEM, it turns it into DER by itself. If that also fails, convert it on the laptop and point the Fob at the DER file:
```
python -c "import ssl; open('broker-ca.der','wb').write(ssl.PEM_cert_to_DER_cert(open('broker-ca.pem').read()))"
```
Then upload `broker-ca.der` to `/certs` and set `MQTT_CA_FILE = "/certs/broker-ca.der"`.

### Reading the Fob's log
Every press ends with one line, for example:
```
SEND_RESULT ctr=212 kind=SUSPICIOUS path=wifi result=confirmed ms=840 reason=-
```
`reason` says why WiFi was not used: `wifi_off`, `wifi_join_failed`, `dns_failed`, `tls_failed`, `connect_timeout`, `connect_failed`, `no_server_ack`, `clock_not_set`, `ca_missing`, `ackcheck_missing`, `budget_exceeded`, or `-`. `field_log.py` puts `path`, `result`, `ms` and `reason` in the CSV.
