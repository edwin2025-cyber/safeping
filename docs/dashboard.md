# SafePing Dashboard (version 4)

The staff dashboard is a React app in `dashboard/`. Flask in `server/` serves it and its API.

Screenshots of every screen, in light and dark, are in [docs/screenshots/](screenshots/). They use a demo database with made-up students. The Overview ones come in two sizes: `overview-7d-light.png` is 1440 x 900, and `overview-7d-laptop-light.png` is 1280 x 650 (a laptop at 100% zoom).

Icons by Font Awesome Free (fontawesome.com), CC BY 4.0.

## What it does

The sidebar has three pages under Monitor (Overview, Live and Devices), plus Settings, which opens over the page. The dashboard opens on the last page used, and on Live the first time.

### Overview

Big numbers and charts for a date range, all on one screen with no scrolling at 1280 x 650 and larger. Only a window under about 600 px tall (or under 1100 px wide) scrolls. Pick the range in the dropdown at the top right: Today, Last 7 days (the default), Last 30 days, This month, or Custom (two date inputs). The range shows next to the title. Export CSV downloads every alert in the range (PDF reports come later).

The page has three rows:

| Row | What it shows |
|---|---|
| 1 | Five stat tiles: Alerts, Time to acknowledge, Open now, Fobs active, Low battery |
| 2 | Alerts over time (two thirds) and Response flow (one third) |
| 3 | Hotspots and System health, side by side |

**Stat tiles.** Each has an icon and a label, a big number and a context line. The context line has a color only when it means something. Open now goes to Live, and Fobs active and Low battery go to Devices.

| Tile | Number | Context line |
|---|---|---|
| Alerts | Alerts in the range, with a small line of this period per day (per hour for Today) | "Up 12% vs previous 7 days" in red, "Down ..." in green, gray when the same or when the previous period had none |
| Time to acknowledge | The median, like "1.0 min median", or "No data" | The type with the lowest median: "Medical fastest, 0.6 min" |
| Open now | Open alerts right now | "2 Medical" in red when any open alert is MEDICAL, else "None urgent" |
| Fobs active | "3 of 4" | "All seen today" in green, or "1 not seen in 24 h" in orange |
| Low battery | Fobs under 20%, orange when more than 0 | The student and percent when there is one, "2 students" when more, "All above 20%" when none |

**Alerts over time.** This period is a solid blue line with a soft area, the previous period of the same length a dashed gray line. Hover a day for its total, the count per type (Medical, Suspicious, Silent, with their icons) and the previous period. Today shows hours instead of days.

**Response flow.** Received, Acknowledged and Resolved, each with its count, its share of Received, and a bar as long as that share. Under Acknowledged and Resolved is the median time for that step. STATUS check-ins are not counted.

**Hotspots.** Where alerts happen: the 5 places with the most alerts in the range, with a bar scaled to the top place. "and N more places" counts the rest. Rows are not links, because Live only shows current alerts and the range is usually in the past.

**System health.** Whether the system itself is working:

| Row | How it is worked out |
|---|---|
| Delivery | Alerts received in the range by link: LoRa, WiFi, and Unknown (older alerts and test tools). STATUS check-ins are included here, because this row is about the radio path and check-ins use it too |
| Duplicates caught | "Not tracked". The server cannot tell a Fob sending the same message again from someone replaying a captured message: both fail the counter check and are counted under Rejected messages as "replay". The Relay already drops LoRa resends before they reach the server |
| Rejected messages | Messages the server turned away in the range, from the `rejected` table, with the count per reason under it ("3 bad signature, 1 replay"). Red with a warning icon when any are bad signature or replay |
| Fobs not seen in 24 h | Fobs with no message of any type, STATUS included, in the last 24 hours, with their names. Orange when any |
| Low battery | Fobs whose newest battery reading is under 20%, with names and percents. Orange when any |
| Reference sensor | "Last reading 2 min ago". Orange when there is no reading, or the reading is older than `REF_MAX_AGE_S` (then floors cannot be worked out) |

How each number is worked out:

- Days and hours use the time zone of the computer the server runs on. `/api/stats` says which one in `tz`.
- STATUS check-ins are left out of every number except Delivery and Fobs active, the same way Live leaves them out of its open count. The CSV export has every alert, STATUS included.
- An alert belongs to the range by the time the server received it. Both ends of the range count: Nov 2 to Nov 8 is 7 days.
- Change line: (this total minus previous total) divided by the previous total. Up is red and down is green, because more alerts is worse.
- Received, Acknowledged, Resolved: alerts received in the range, and how many of those have been acknowledged or resolved so far.
- Median time to acknowledge: the middle value of (acknowledged time minus received time), for alerts in the range that have an acknowledged time. Alerts with no acknowledged time are left out, never guessed. "No data" means none had one. The per-type medians work the same way, one type at a time.
- Median after acknowledged (Resolved step): the middle value of (resolved time minus acknowledged time), for resolved alerts that have both times. Resolving an alert nobody acknowledged sets both times at once, so it counts as 0 minutes here.
- Open now: alerts that are not acknowledged and not resolved, right now, whatever the range.
- Fobs active: Fobs (not Reference boards) whose newest alert of any type, STATUS included, arrived in the last 24 hours, out of all registered Fobs.
- Low battery: Fobs whose newest battery reading is under 20%, like the Low word on the Devices page.
- Hotspots: an alert with GPS counts for the nearest campus place within 200 m (the same rule as "Near ..." on Live). GPS alerts with no place that close are grouped as "GPS, no named place". Alerts with no GPS are grouped by floor ("Indoors, floor 2") or as "No location". When no alert in the range has a location, the panel says "No alerts with a location in this range."

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
- `data.js` also has 4 fake rejected messages and 2 fake duplicates for System health. Mock mode shows a number for Duplicates caught so the row can be checked with data. The real server says "Not tracked" (see Overview above).
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
- A clustered alert hides its circle. The circle comes back when the cluster splits (after the split animation) or is spread out by a click, so a circle never floats without its marker in the middle.
- The control group in the bottom right: zoom in, zoom out, fit all alerts (in the alert panel: center on the alert), and map labels.
- Zoom moves in half steps, and the mouse wheel is a little gentler (`zoomSnap` 0.5, `wheelPxPerZoomLevel` 90). Fit all flies there in 0.5 s, or jumps when the computer asks for reduced motion.
- A poll (every 3 s) never moves the map. The map fits the open alerts once when Live opens, and flies to a new MEDICAL or SUSPICIOUS alert only when Auto-zoom is on.
- "2 alerts have no GPS" in the top left lists the alerts the map cannot show. Click one to open it.

### Markers and circles move together (fixed in version 4)

Before version 4, markers seemed to stay put while their circles moved, then jumped. The cause was the clustering, not Leaflet's own zoom:

- Circles were drawn on their own, outside the cluster group. A clustered alert still showed its circle, with no marker in the middle (62 of 66 circles in the busiest mock view).
- When zooming changed the clusters, markercluster slid markers into or out of the cluster point for 0.3 s while their circles stayed still. Measured offsets reached 40 to 165 px, then snapped to 0.

Checked and ruled out: no transition or transform on the marker element Leaflet moves (hover effects are on the inner span), no layers recreated on a poll, and markers and circles both follow Leaflet's zoom animation (under 1 px apart for markers that stay on their own).

The fix, in `AlertLayer` (`dashboard/src/components/mapParts.jsx`): one marker and its circles per alert id, kept together and updated in place. Circles live in the overlay pane with the default SVG renderer, markers in the cluster group with `animate: true`. A circle shows only while its marker stands on its own. The Peek map uses the same code for its one alert.

A headless Edge script panned, zoomed (buttons and wheel), used Fit all and waited through polls, and measured every animation frame. After the fix every marker sat within 1 px of its circle's center (2 px on the Peek map) and no frame had a circle without its marker, with and without reduced motion.

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
| `median_ack_by_type` | Median seconds to acknowledge per type, only types that have times. STATUS never appears |
| `hotspots` | `places`: up to 5 rows of `label`, `kind` (`place`, `gps`, `floor` or `none`) and `count`, most first. `more_count`: how many more places there are |
| `delivery` | `lora`, `wifi`, `unknown`: alerts received in the range by link, STATUS included |
| `duplicates` | `null`: not tracked (see System health) |
| `rejected` | `total` and `by_reason` (like `{"bad_signature": 2, "replay": 1}`) for messages rejected in the range |
| `stale_fobs` | Names of Fobs not seen in 24 hours |
| `low_battery_fobs` | `name` and `pct` for each Fob under 20%, lowest first |
| `reference_age_s` | Seconds since the newest Reference reading, or `null` |

The per-day count by type for the tooltip was already there, in `per_day[].by_type` (and `per_hour[].by_type` for one day). `weekday_hour` is no longer used by the dashboard but is still returned.

`/api/export.csv` has one row per alert, oldest first, all types: Received, Type, Student, Fob ID, Status, Place, Floor, Latitude, Longitude, Accuracy (m), Battery (%), Link, Acknowledged, Resolved. Times are `YYYY-MM-DD HH:MM:SS` in the server's time zone. Place is the named place ("Near the bus loop"), empty when there is none. The file is named like `safeping-alerts-2026-11-02-to-2026-11-08.csv`. It starts with a byte order mark so Excel reads names correctly, and a cell that starts with `=`, `+`, `-` or `@` gets a leading `'` so a spreadsheet never runs it as a formula.

The Relay item in the top bar uses `last_lora_age_s`. The Relay sends no heartbeat, so it only says when the last LoRa alert arrived. A quiet Relay shows a gray dot, not a fault.

## Database columns

`server/db.py` adds these to the `alerts` table when they are missing (`ALTER TABLE ... ADD COLUMN`). Existing rows keep their data. Versions 2, 3 and 4 added no columns. The acknowledge time Overview needs was already stored in `acknowledged_at`: Acknowledge sets it, and Resolve sets it too when it is empty.

Rejected messages were already stored: `processor.process()` writes a row to the `rejected` table (`timestamp`, `device_id` when known, `reason`, and the first 300 characters of the message) every time it turns a message away. Version 4 only reads it, and adds an index on its `timestamp` (`CREATE INDEX IF NOT EXISTS`, safe on an old database). No accept or reject decision changed.

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

Design tokens are in `dashboard/src/styles/tokens.css`, with a light and a dark block. The app uses only these font sizes: 12, 13, 14, 16, 20, 24, 28, 32 px. Panel and section spacing uses 4, 8, 12, 16, 20, 24 and 32 px (tags use 6 px side padding). Numbers use tabular figures everywhere, and big numbers are semibold (600).

Dark theme, "Midnight": deep and crisp. Thin, visible borders separate the layers, not big jumps in shade. Every raised and overlay surface has its 1 px border, and overlays also get a shadow, so nothing looks see-through.

| Token | Dark (rgb) | Used for |
|---|---|---|
| `page`, `surface` | 15,16,18 | Page, tables, inputs |
| `sidebar` | 11,12,14 | Sidebar |
| `surface-raised` | 22,23,26 | Chart panels, stat tiles, map controls |
| `surface-overlay` | 22,23,26 | Peek, Settings, menus, popovers, tooltips |
| `border-raised` | 38,40,45 | 1 px border on every raised surface |
| `border-overlay` | 44,46,52 | 1 px border on every overlay |
| `surface-hover` | 26,27,31 | Hover |
| `surface-selected` | 36,38,43 | Selected nav item, tab, segment |
| `border` | 30,32,36 | Dividers in tables and lists, chart gridlines |
| `border-bold` | 52,55,61 | Chart cursor |
| `text`, `text-subtle`, `text-subtlest` | 237,237,239 / 180,183,190 / 138,143,152 | Text |
| `backdrop` | black at 60%, with a blur | Behind Peek and Settings |
| `shadow-overlay` | 0 16px 48px black at 60%, plus a 1 px white ring at 4% | Overlays |

Tag backgrounds in dark (the `subtler` tokens) are deep tints, so tags glow a little: red 58,29,26, yellow 58,50,20, purple 46,30,64, green 22,52,40, orange 58,38,16, blue 22,36,64, teal 18,44,52, gray 36,38,43. The open MEDICAL row tint is 40,22,20. The Dark Matter map tiles are unchanged.

- Sidebar: Midnight in both themes (background 15,16,18 in light and 11,12,14 in dark), with its own `--color-sb-*` tokens, so the brand looks the same in both. The light theme keeps a white content area.
- Chart panels and stat tiles use `--color-panel` (white in light, 22,23,26 in dark) with a 1 px border and 8 px corners. Lists never get boxes.
- Chart colors: this period blue bold, previous period gray bold dashed, Hotspots bars and the sparkline blue bold. Response flow uses `--color-flow-1` to `-3`, one blue family: darker for later steps in light, brighter for later steps in dark.
- Icons: Font Awesome 6 Free, solid style. All of them are named in one map, `dashboard/src/lib/icons.js`, so changing an icon is a one-line edit. Icons take the color of the text around them: 14 px in tags, table cells and System health rows, 16 px in nav, buttons and tile labels, with fixed width in the nav and property lists so labels line up.

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
- Chart lines, the sparkline and Hotspots bars pass 3:1 against their panel. The script lists the Response flow bars as "info", not pass or fail: a light-to-dark scale has to start near the background, and every bar has its count written next to it.
- The Midnight values passed as given in version 4. No color had to change for contrast. Panel and overlay borders are listed as "info": they separate layers and carry no meaning on their own.

Inputs and dropdowns use the quiet 1 px border, as specified. Their placeholder or label identifies them, so they do not need a 3:1 border. Map tile colors in the script are approximate.
