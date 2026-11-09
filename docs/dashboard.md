# SafePing Dashboard (version 1)

The staff dashboard is a React app in `dashboard/`. Flask in `server/` serves it and its API.

## What it does

- **Live**: the alert list on the left and a map on the right. New alerts show up within 3 seconds. Click a card (or press Enter or Space on it) to open the alert in a centered panel with its own map, all details, and the buttons Acknowledge, Resolve and Copy details.
- **Devices**: one row per registered device: name, ID, role, last seen, battery, last counter, link (LoRa or WiFi) and open alerts.
- **Settings**: saved in the browser (localStorage) and applied right away.

Sort order is the same as the old dashboard: open alerts first, then by type (SILENT, MEDICAL, SUSPICIOUS, STATUS), then newest.

Alert states:

| State | Meaning | Where it shows |
|---|---|---|
| Open | Nobody has acknowledged it | Live list, open count |
| Acknowledged | Someone saw it and is on it | Live list (faded marker) |
| Resolved | It is handled | Gone from the Live list. Kept in the database |

Resolving an alert also acknowledges it if nobody did yet.

## Run it

### Development (live reload)

Two PowerShell windows:

```
cd server
$env:NO_MQTT = "1"        # leave this out if the broker is running
python app.py
```

```
cd dashboard
npm install               # first time only
npm run dev
```

Open the address Vite prints (http://localhost:5173). Vite passes every `/api` request to Flask on port 5000.

### Production (one server)

```
cd dashboard
npm run build
cd ..\server
python app.py
```

Open http://127.0.0.1:5000. Flask serves `dashboard/dist` at `/`. If `dashboard/dist` does not exist, Flask serves the old dashboard in `server/static` instead.

## Map tiles and CARTO_KEY

With a CARTO key the map uses CARTO raster basemaps: Positron in the light theme and Dark Matter in the dark theme. Set the key in the window that runs Flask:

```
$env:CARTO_KEY = "paste-your-carto-basemaps-key-here"
python app.py
```

Never put the key in a file in this repo. `/api/config` hands it to the browser, because the browser loads the tiles, so anyone who can open the dashboard can see it. Use a key restricted to the hosts the dashboard runs on (CARTO wants a separate key for `localhost` and `127.0.0.1`).

Tile URL used:

```
https://{s}.basemaps.cartocdn.com/rastertiles/<style>/{z}/{x}/{y}{r}.png?key=<key>
```

`{s}` is a, b, c or d. `<style>` is `light_all`, `light_nolabels`, `dark_all` or `dark_nolabels`. `{r}` is `@2x` on high-density screens.

Without a key the map uses OpenStreetMap tiles. In the dark theme those tiles are dimmed with a CSS filter. The map labels setting only works with a CARTO key.

The attribution (OpenStreetMap contributors, and CARTO when used) is always shown on every map.

## Settings

| Setting | Choices | Default |
|---|---|---|
| Theme | Auto (follows the computer), Light, Dark | Auto |
| Time format | 12 h, 24 h | 12 h |
| Show STATUS check-ins | on, off | off |
| Alert sound | on, off, plus a Test sound button | off |
| Auto-zoom the map to new alerts | on, off | on |
| Map labels | on, off (needs a CARTO key) | on |
| Sight radius for SUSPICIOUS | 25, 50, 100 m | 50 m, from `/api/config` |
| Camera review window | minutes before, minutes after | 2 and 5, from `/api/config` |

Reset to defaults puts all of them back.

The alert sound is a short tone made in the browser (no audio files). It plays for new MEDICAL and SUSPICIOUS alerts. Browsers block sound until the page is clicked once. Turning the sound on counts as that click. After a reload, the first click or key press anywhere unlocks it again.

## Map circles

Each alert with a GPS fix gets a marker and a circle. Radius is in meters.

- MEDICAL, SILENT, STATUS: radius = `acc`, the GPS accuracy the Fob sends.
- SUSPICIOUS: radius = `acc` + sight radius. This is the area the student could see. It does not grow over time. It is drawn dashed, with a smaller solid circle of radius `acc` inside.

Example: GPS accuracy 12 m and sight radius 50 m gives a 62 m circle. The panel shows "Area: 62 m (GPS 12 m + sight 50 m)".

Alerts with no GPS fix get no marker. Their location line says "Indoors, floor N" when the server worked out a floor, otherwise "Location unknown".

## Camera review window (SUSPICIOUS)

The panel for a SUSPICIOUS alert has a "Review cameras" box:

- Window: from the received time minus the minutes before, to the received time plus the minutes after.
- Area: the center and circle radius, or "Indoors, floor N".

The Copy button copies:

```
SafePing SUSPICIOUS alert
Student: <name> (<device id>)
Pressed: <date> <time>
Review cameras: <start> to <end>
Area: within <r> m of <lat>, <lon>
```

"Pressed" is the time the server received the alert, because the Fob clock can be wrong.

## API added for the dashboard

| Route | What it returns |
|---|---|
| `GET /api/config` | `carto_key` (or null), `pa_per_floor`, `ref_max_age_s`, `defaults` |
| `GET /api/devices` | One row per device. Never includes the secret key |
| `POST /api/resolve` | Body `{"id": 12}`. Same style as `/api/ack` |
| `GET /api/status` | Now also has `last_lora_age_s`: seconds since the last alert that came in over LoRa |
| `GET /api/alerts` | Resolved alerts are left out. Add `resolved=1` to include them |

The Relay pill in the top bar uses `last_lora_age_s`. The Relay sends no heartbeat, so the pill only says when the last LoRa alert arrived. A quiet Relay shows gray, not as a fault.

## Database columns added

`server/db.py` adds these to the `alerts` table when they are missing (`ALTER TABLE ... ADD COLUMN`). Existing rows keep their data and get the default.

| Column | Meaning |
|---|---|
| `resolved`, `resolved_at` | Resolve action |
| `link` | `lora` (serial bridge), `wifi` (MQTT) or `unknown` (older alerts, test tools) |
| `temperature` | The Fob's `t`, hundredths of a degree C |
| `counter` | The message's `ctr` |

The link is set by the code that received the message: `serial_bridge.py` says `lora`, `mqtt_listener.py` says `wifi`. It never changes whether a message is accepted. When the Relay starts republishing over MQTT (planned), its alerts will show as WiFi until the Relay path gets its own topic.

## Login hook

`server/app.py` has a `require_login` decorator on every `/api/*` route and on the dashboard routes. It lets everything through for now. Login and two-factor go there. They must be checked on the server, not only in the page. The older optional `DASHBOARD_PASSWORD` check still runs before it.

## Colors and contrast

Design tokens are in `dashboard/src/styles/tokens.css`, with a light and a dark block. Check contrast after any color change:

```
cd dashboard
npm run contrast
```

It checks every text and background pair the dashboard uses, in both themes (text 4.5:1, meaningful shapes and borders 3:1). Changes made so every pair passes:

- The open MEDICAL card border uses red bold, not red border (red border was 2.78:1 light, 2.87:1 dark).
- The time on an open MEDICAL card uses text subtle, not text subtlest (4.48:1 light).
- Switch tracks and input borders use text subtlest, not border bold (2.85:1 dark).
- The SUSPICIOUS dashed circle uses yellow text in the light theme, not yellow border (about 1.9:1 on light tiles).

Map tile colors in the script are approximate.
