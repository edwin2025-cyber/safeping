# SafePing Dashboard (version 3)

The staff dashboard is a React app in `dashboard/`. Flask in `server/` serves it and its API.

Screenshots of every screen, in light and dark, are in [docs/screenshots/](screenshots/). They use a demo database with made-up students.

## What it does

The sidebar has three pages under Monitor (Overview, Live and Devices), plus Settings, which opens over the page. The dashboard opens on the last page used, and on Live the first time.

### Overview

Big numbers and charts for a date range. Pick the range in the dropdown at the top right: Today, Last 7 days (the default), Last 30 days, This month, or Custom (two date inputs). The range shows under the title. Export CSV downloads every alert in the range (PDF reports come later).

| Section | What it shows |
|---|---|
| Alerts | The total for the range, the change against the previous period of the same length, and a line chart per day: this period solid blue, the previous period dashed gray. Today shows hours instead of days |
| Summary | Median time to acknowledge, Open now, Fobs active, Low battery. Click Open now to go to Live, or Fobs active or Low battery to go to Devices |
| Response flow | Received, Acknowledged and Resolved, with the share of Received and the median time between steps |
| Alerts by type | A line per type per day. STATUS is off until you turn on "Include STATUS" |
| When alerts happen | Weekday (rows) by hour (columns). Darker blue means more alerts. Hover a cell for the count |

How each number is worked out:

- Days and hours use the time zone of the computer the server runs on. `/api/stats` says which one in `tz`.
- STATUS check-ins are left out of every number except "Alerts by type" with Include STATUS on, the same way Live leaves them out of its open count. The CSV export has every alert, STATUS included.
- An alert belongs to the range by the time the server received it. Both ends of the range count: Nov 2 to Nov 8 is 7 days.
- Change line: (this total minus previous total) divided by the previous total. Up is red and down is green, because more alerts is worse. When the previous period had none, it says "No alerts in the previous period".
- Received, Acknowledged, Resolved: alerts received in the range, and how many of those have been acknowledged or resolved so far.
- Median time to acknowledge: the middle value of (acknowledged time minus received time), for alerts in the range that have an acknowledged time. Alerts with no acknowledged time are left out, never guessed. "No data" means none had one.
- Median after acknowledged (Resolved step): the middle value of (resolved time minus acknowledged time), for resolved alerts that have both times. Resolving an alert nobody acknowledged sets both times at once, so it counts as 0 minutes here.
- Open now: alerts that are not acknowledged and not resolved, right now, whatever the range. Red when one of them is MEDICAL.
- Fobs active: Fobs (not Reference boards) whose newest alert of any type, STATUS included, arrived in the last 24 hours, out of all registered Fobs.
- Low battery: Fobs whose newest battery reading is under 20%, like the Low word on the Devices page.
- Heat grid colors: no alerts is gray, then four steps of blue up to the busiest hour. Under 7 days the full week still shows, with the note "Based on the selected range".

Every chart has a text summary for screen readers and a hidden table of its numbers. Charts do not animate when the computer asks for reduced motion. The charts use recharts (MIT license). The Overview code loads only when the page is opened, so Live stays fast.

### Live

Three views, picked with the tabs next to the title. The browser remembers the choice.

| View | What you see |
|---|---|
| Split (default) | Alert table on the left, map on the right, split by a thin line |
| List | The alert table, full width |
| Map | The map, edge to edge, with a floating alert list you can hide |

Tools on the right of the title row:

- Filter: one alert type, or all types.
- Search: student name or Fob ID.
- Needs action, Acknowledged, All. All also shows resolved alerts, grouped under quiet headers.

Table columns: Type, Student (with the Fob ID), Place, Time, Status. Status shows only under Acknowledged and All, because every row under Needs action is Open. In Split view the place moves under the name. An open MEDICAL row has a light red tint. Hovering a row lights up its marker on the map, and hovering a marker lights up its row.

Sort order is the same as before: open alerts first, by type (SILENT, MEDICAL, SUSPICIOUS, STATUS), then newest. Then acknowledged, then resolved.

Click a row (or press Enter on it) to open the alert in a large center panel. It shows every property, the camera review box for SUSPICIOUS alerts, and a map. Acknowledge and Resolve sit under the name. Esc closes it and focus goes back to the row.

### Devices

One row per registered device: Student, Fob ID, Last seen, Battery, Link and Open alerts. Click a row to see that device's details and its alert history (newest 200, with a type filter).

### Alert states

| State | Meaning | Where it shows |
|---|---|---|
| Open | Nobody has acknowledged it | Needs action |
| Acknowledged | Someone saw it and is on it | Acknowledged |
| Resolved | It is handled | All, under Resolved. Kept in the database |

Resolving an alert also acknowledges it if nobody did yet.

### Keyboard

| Keys | What it does |
|---|---|
| Ctrl+K | Go to Live and search alerts |
| Ctrl+\ | Open or close the sidebar |
| Enter | Open the focused row |
| Esc | Close a panel, menu or Settings |

## Run it

Use `npm.cmd`, not `npm`, in PowerShell on the school laptop.

### Development (live reload)

Two PowerShell windows:

```
cd server
$env:NO_MQTT = "1"        # leave this out if the broker is running
python app.py
```

```
cd dashboard
npm.cmd install           # first time only
npm.cmd run dev
```

Open the address Vite prints (http://localhost:5173). Vite passes every `/api` request to Flask on port 5000.

### Mock mode (no Flask)

For UI work without the server:

```
cd dashboard
npm.cmd run dev:mock
```

This runs `vite --mode mock`. The dashboard then answers every `/api` call from fake data in the browser and never calls Flask.

- The fake data is in `dashboard/src/mock/data.js`: 8 current alerts (all 4 types, all 3 states), 4 devices, 4 places. All names are made up.
- `dashboard/src/mock/api.js` adds about 60 days of history so Overview looks real: 0 to 6 alerts a day, more on weekdays between 7 AM and 4 PM, mostly STATUS. It is seeded by the date, so a given day always has the same alerts. History alerts are resolved and have acknowledge and resolve times.
- The fake routes are in `dashboard/src/mock/api.js`, including `/api/stats`. Export CSV builds the file in the browser from the mock rows. Acknowledge and Resolve work, but only in memory. A page reload starts over.
- A new random alert arrives every 45 seconds, so the sound and auto-zoom can be tested.
- Without a CARTO key the map uses OpenStreetMap tiles (see below to add one).
- The top bar shows an orange "Mock data" tag.

To see CARTO tiles in mock mode, make the file `dashboard/.env.mock.local` with one line:

```
VITE_CARTO_KEY=paste-your-carto-basemaps-key-here
```

Vite reads it only in mock mode. Git ignores it (`.env.*` in `.gitignore`), so never commit it or copy the key anywhere else. Restart `npm.cmd run dev:mock` after changing it. Without the file, the map falls back to OpenStreetMap. In normal mode the key still comes from `/api/config` (the `CARTO_KEY` the server was started with).

Normal `npm.cmd run dev` and `npm.cmd run build` are unchanged. The mock files are left out of the build.

### Production (one server)

```
cd dashboard
npm.cmd run build
cd ..\server
python app.py
```

Open http://127.0.0.1:5000. Flask serves `dashboard/dist` at `/`. If `dashboard/dist` does not exist, Flask serves the old dashboard in `server/static` instead.

## Campus places

`server/places.json` names places on campus, so staff read "Near the basketball courts" instead of a GPS point. It starts as an empty list `[]`.

Example (do not copy these numbers, they are not the campus):

```json
[
  {"name": "the front entrance", "lat": 34.73040, "lon": -86.58610},
  {"name": "the basketball courts", "lat": 34.73250, "lon": -86.58350},
  {"name": "the student parking lot", "lat": 34.72900, "lon": -86.58800}
]
```

- Write each name the way it should read after "Near" and "of", so usually starting with "the". The dashboard adds the first capital letter itself.
- Get coordinates by right-clicking the spot in Google Maps. Use at least 5 decimals.
- The server reads the file again whenever it changes. No restart needed.
- A broken entry is skipped and printed in the server window.
- Settings > Campus places shows the list the server loaded.

How a GPS alert is described:

| Nearest place | Shown as |
|---|---|
| Within 40 m | "Near the basketball courts" |
| 40 to 200 m | "120 m NE of the front entrance" (distance rounded to 10 m) |
| Farther, or no places | "GPS, about 12 m" |
| No GPS | "Indoors, floor 2", or "Unknown" |

The direction is from the place to the alert (N, NE, E, SE, S, SW, W, NW). Copy details and Copy for security add a "Place:" line when there is a named place.

For testing, `SAFEPING_PLACES` can point the server at another places file, the same way `SAFEPING_DB` points at another database.

## Map

### Tiles and CARTO_KEY

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

Without a key the map uses OpenStreetMap tiles, dimmed with a CSS filter in the dark theme. The labels button only works with a CARTO key.

The attribution (OpenStreetMap contributors, and CARTO when used) is always shown on every map, at 12 px.

### Markers, clusters and controls

- Each alert with GPS gets a 28 px marker in its type color with the type icon. Acknowledged and resolved markers are smaller and faded.
- Markers close together merge into a cluster with a count (leaflet.markercluster, MIT license). The ring turns red when an open MEDICAL alert is inside. Click a cluster to zoom in; at the closest zoom it spreads the markers out.
- The control group in the bottom right: zoom in, zoom out, fit all alerts (in the alert panel: center on the alert), and map labels.
- "2 alerts have no GPS" in the top left lists the alerts the map cannot show. Click one to open it.

### Circles

Radius is in meters.

- MEDICAL, SILENT, STATUS: radius = `acc`, the GPS accuracy the Fob sends.
- SUSPICIOUS: radius = `acc` + sight radius. This is the area the student could see. It does not grow over time. It is drawn dashed, with a smaller solid circle of radius `acc` inside.

Example: GPS accuracy 12 m and sight radius 50 m gives a 62 m circle. The panel shows "Area: 62 m (GPS 12 m + sight 50 m)".

## Camera review window (SUSPICIOUS)

The alert panel for a SUSPICIOUS alert has a "Review cameras" box:

- Window: from the press time minus the minutes before, to the press time plus the minutes after.
- Area: the place (when known), the center and circle radius, or "Indoors, floor N".

"Copy for security" copies:

```
SafePing SUSPICIOUS alert
Student: <name> (<device id>)
Pressed: <date> <time>
Place: <place, only when there is a named place>
Review cameras: <start> to <end>
Area: within <r> m of <lat>, <lon>
```

"Pressed" is the time the server received the alert, because the Fob clock can be wrong.

## Settings

Settings open in a large window from the sidebar (Settings, or the account menu). They are saved in this browser and apply right away. "Search settings" finds rows across all sections.

| Section | Setting | Choices | Default |
|---|---|---|---|
| Appearance | Theme | Use system setting, Light, Dark | Use system setting |
| Appearance | Time format | 12 h, 24 h | 12 h |
| Alerts | Alert sound, with Test sound | on, off | off |
| Alerts | Show STATUS check-ins | on, off | off |
| Map | Auto-zoom to new alerts | on, off | on |
| Map | Map labels | on, off (needs a CARTO key) | on |
| Camera review | Sight radius | 25, 50, 100 m | 50 m, from `/api/config` |
| Camera review | Minutes before, minutes after | 0 to 60 | 2 and 5, from `/api/config` |
| Campus places | Read-only list from `server/places.json` | | |
| About | Server version, pressure per floor, map key set (Yes or No), registered devices, Reset to defaults | | |

The alert sound is a short tone made in the browser (no audio files). It plays for new MEDICAL and SUSPICIOUS alerts. Browsers block sound until the page is clicked once. Turning the sound on counts as that click. After a reload, the first click or key press anywhere unlocks it again.

The server version is `VERSION` in `server/app.py` (bump it by hand) plus the git commit the server runs from, when git is available.

## API used by the dashboard

| Route | What it returns |
|---|---|
| `GET /api/alerts` | Alerts. `status=1` adds STATUS, `resolved=1` adds resolved. Each alert also has `place_name`, `place_distance_m` and `place_bearing` (null when there is no named place within 200 m) |
| `POST /api/ack`, `POST /api/resolve` | Body `{"id": 12}` |
| `GET /api/status` | Server time, Reference pressure and age, `last_lora_age_s` |
| `GET /api/config` | `carto_key` (or null), `pa_per_floor`, `ref_max_age_s`, `defaults`, `version`, `commit` |
| `GET /api/devices` | One row per device. Never includes the secret key |
| `GET /api/devices/<id>/alerts` | That device's alerts, all types and states, newest first, up to 200. 404 for an unknown device |
| `GET /api/places` | The places from `places.json` |
| `GET /api/stats?from=2026-11-02&to=2026-11-08` | Everything Overview shows, in one answer (below) |
| `GET /api/export.csv?from=2026-11-02&to=2026-11-08` | Every alert in the range as a CSV download (below) |

Both new routes are behind `require_login`, like the others. `from` and `to` are dates (`YYYY-MM-DD`), both included, at most 366 days. A missing or wrong date gets a 400 with `{"ok": false, "error": "..."}` that says what is wrong.

`/api/stats` fields:

| Field | Meaning |
|---|---|
| `from`, `to`, `days` | The range |
| `previous_from`, `previous_to` | The previous period of the same length, just before |
| `tz`, `tz_offset_min` | The server's time zone name and its offset from UTC in minutes |
| `server_time` | Unix seconds |
| `total`, `previous_total` | Alerts in the range and in the previous period, STATUS left out |
| `per_day` | One row per day: `date`, `count` (no STATUS), `by_type` (all four types), `previous_date`, `previous_count` |
| `per_hour` | Only for a one-day range, else null. One row per hour: `hour`, `count`, `by_type`, `previous_count` |
| `weekday_hour` | 7 rows (Monday first) of 24 counts (hour 0 to 23), STATUS left out |
| `flow` | `received`, `acknowledged`, `resolved`, `median_ack_s`, `median_resolve_s` (null when no times), `ack_timed` and `resolve_timed` (how many alerts the medians use) |
| `open_now`, `open_medical_now` | Open alerts right now, whatever the range |
| `fobs_active`, `fobs_total` | Fobs seen in the last 24 hours, and all registered Fobs |
| `low_battery` | Fobs whose newest battery reading is under 20% |

`/api/export.csv` has one row per alert, oldest first, all types: Received, Type, Student, Fob ID, Status, Place, Floor, Latitude, Longitude, Accuracy (m), Battery (%), Link, Acknowledged, Resolved. Times are `YYYY-MM-DD HH:MM:SS` in the server's time zone. Place is the named place ("Near the bus loop"), empty when there is none. The file is named like `safeping-alerts-2026-11-02-to-2026-11-08.csv`. It starts with a byte order mark so Excel reads names correctly, and a cell that starts with `=`, `+`, `-` or `@` gets a leading `'` so a spreadsheet never runs it as a formula.

The Relay item in the top bar uses `last_lora_age_s`. The Relay sends no heartbeat, so it only says when the last LoRa alert arrived. A quiet Relay shows a gray dot, not a fault.

## Database columns

`server/db.py` adds these to the `alerts` table when they are missing (`ALTER TABLE ... ADD COLUMN`). Existing rows keep their data. Versions 2 and 3 added no columns. The acknowledge time Overview needs was already stored in `acknowledged_at`: Acknowledge sets it, and Resolve sets it too when it is empty.

| Column | Meaning |
|---|---|
| `resolved`, `resolved_at` | Resolve action |
| `link` | `lora` (serial bridge), `wifi` (MQTT) or `unknown` (older alerts, test tools). The dashboard only shows LoRa or WiFi |
| `temperature` | The Fob's `t`, hundredths of a degree C |
| `counter` | The message's `ctr`, shown as "Message number" |

When the Relay starts republishing over MQTT (planned), its alerts will show as WiFi until the Relay path gets its own topic.

## Login hook

`server/app.py` has a `require_login` decorator on every `/api/*` route and on the dashboard routes. It lets everything through for now. Login and two-factor go there. They must be checked on the server, not only in the page. The account menu already has a disabled "Log out" for that work. The older optional `DASHBOARD_PASSWORD` check still runs before it.

## Look and colors

Design tokens are in `dashboard/src/styles/tokens.css`, with a light and a dark block. The app uses only these font sizes: 12, 13, 14, 16, 20, 24, 28, 32 px. Panel and section spacing uses 4, 8, 12, 16, 20, 24 and 32 px (tags use 6 px side padding, heat grid cells 2 px gaps). Numbers use tabular figures everywhere, and big numbers are semibold (600).

- Dark theme: solid charcoal (page 31,31,33). Raised surfaces (Peek, Settings, menus, popovers, chart panels) are lighter (43,44,47) and always have a 1 px border (61,63,67). The backdrop is black at 55% with a blur.
- Sidebar: charcoal in both themes, with its own `--color-sb-*` tokens. The light theme keeps a white content area.
- Chart panels use `--color-panel` (white in light, 43,44,47 in dark) with a 1 px border and 8 px corners. Lists never get boxes.
- Chart colors: MEDICAL red bold, SUSPICIOUS `--color-chart-yellow` (179,134,0 in light), SILENT purple bold, STATUS gray bold, this period blue bold, previous period gray bold dashed. Response flow and the heat grid use `--color-flow-*` and `--color-heat-*`, one blue family.

Check contrast after any color change:

```
cd dashboard
npm.cmd run contrast
```

It checks every text and background pair the dashboard uses, in both themes (text 4.5:1, meaningful shapes and borders 3:1). Choices made so every pair passes:

- Muted text on an open MEDICAL row uses text subtle, not text subtlest (4.48:1 light).
- Switch tracks (off) use text subtlest, not border bold (2.85:1 dark).
- The SUSPICIOUS dashed circle uses yellow text in the light theme, not yellow border (about 1.9:1 on light tiles).
- Cluster rings use text subtlest, not border bold (2.82:1 on light OpenStreetMap tiles).
- The app mark uses the same blue in both themes, so the white shield always reads.
- The account note under "Safety office" brightens to the sidebar text color on hover (the muted label color is 4.02:1 on the hover gray in light).
- SUSPICIOUS chart lines use 179,134,0 in light (3.32:1 on white), not the yellow bold of the tags and markers.
- Lines and the busiest heat cell pass 3:1 against their panel. The script lists the lower heat steps and the Response flow blocks as "info", not pass or fail: a light-to-dark scale has to start near the background, and every flow block has its count written above it. Hover a heat cell, or use the hidden table, for the exact count.

Inputs and dropdowns use the quiet 1 px border, as specified. Their placeholder or label identifies them, so they do not need a 3:1 border. Map tile colors in the script are approximate.
