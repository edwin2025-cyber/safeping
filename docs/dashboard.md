# SafePing Dashboard (version 5)

The staff dashboard is a React app in `dashboard/`. Flask in `server/` serves it and its API.

Screenshots of every screen, in light and dark, are in [docs/screenshots/](screenshots/). They come from mock mode, with made-up students. The Overview ones come in four sizes: `overview-light.png` is 1440 x 900, `overview-laptop-light.png` is 1280 x 650 (a laptop at 100% zoom), `overview-wide-light.png` is 1920 x 1080 and `overview-narrow-light.png` is 1080 x 900. `overview-font-*.png` show Overview in each test font, and `settings-dropdown-*.png` shows an open dropdown. `overview-empty-*.png` and `live-empty-*.png` show the empty dashboard preview, and `device-peek-*.png` shows the device panel.

Changes after the first version 5 pass: the light theme is pure white again (the version 4 values), types and links are colored tags again, Overview has a Busy hours chart next to a smoother Alerts chart, Live Split view has a divider you can drag, row buttons have their own column, dropdowns open a styled list, and the sidebar opens and closes smoothly.

Then: the font is Satoshi with General Sans digits, Open and the Mock data tag are magenta, Suspicious is a deep gold, the alert panel is arranged in sections, Review cameras is a plain card, Copy details and Copy for security also copy a formatted table, Export offers an Excel workbook, Busy hours shades each bar by its count, and the Alerts chart grows in and its hover dots glide.

Latest: Suspicious is magenta, the link tags are three grays (Unknown, LoRa, WiFi), Review cameras is blue, Busy hours is blue, the Mock data tag is gray, and Custom opens a calendar. The alert panel hides the GPS point until you ask for it. The device panel is in sections too. The Last alert tile has room for letters like "g" in "ago". Settings can show an empty, first-day dashboard to check that nothing breaks with no data.

Icons by Font Awesome Free (fontawesome.com), CC BY 4.0.

## What it does

The sidebar has "Find a student", three pages under Monitor (Overview, Live and Devices), and Settings under Workspace, which opens over the page. The dashboard opens on the last page used, and on Live the first time.

### Sidebar

- The top shows the wordmark "SafePing" and the button that folds the sidebar (Ctrl+\). Folded, an "S" shows instead, and it turns into the open button when you point at it.
- Folding and opening is smooth: the width slides over about 0.2 s, labels fade, and icons stay in the same place. No animation when the computer asks for reduced motion.
- "Find a student" opens the search (below). It is a row, not a search box. "Ctrl+K" appears on the right, with a faint rectangle behind the row, only when you point at it or tab to it.
- Live shows the open count on the right. The count is a red pill when an open MEDICAL or SILENT alert exists, and muted text otherwise.
- The bottom shows "Server online" and the account row ("Safety office", "Login coming soon"). The "SO" circle has its own gray and a thin ring, so it stays visible when the row is hovered.
- Under 1280 px wide the sidebar folds to icons by itself. The fold button still opens it. The choice you make on a wide window is remembered.

### Find a student

A search box in the top third of the screen. Open it with "Find a student" or Ctrl+K from anywhere.

- Results update as you type, in two groups. Students: the name, the Fob ID, and the last alert as a type icon and a time. Recent alerts: matching alerts, newest first, with the type icon, the student and the place.
- With nothing typed it shows every student and the 5 newest alerts.
- It matches the student name or the Fob ID. Up and Down move, Enter opens, Esc closes. A student opens the device panel, an alert opens the alert panel.
- STATUS check-ins show only when Settings > Alerts > Show STATUS check-ins is on.
- It uses `GET /api/search` (below).

Live keeps its own table filter (the search icon in the Live toolbar). It only filters the Live table.

### Top bar

Relay, Reference and the server clock sit together on the right, as plain 13 px text with thin dividers. Relay and Reference have a status dot. Each value has a fixed width (the width of its widest possible text, with tabular numbers), so nothing moves when a value changes. The clock shows no seconds ("5:53 PM" or "17:53") and updates every 15 seconds. Hover or focus an item for what it means.

### Overview

Four stat tiles, the Alerts chart and Busy hours side by side (two thirds and one third), and then the map and Recent activity side by side, all on one screen with no scrolling at 1280 x 650 and larger. Pick the range in the dropdown at the top right: Today, Last 7 days (the default), Last 30 days, This month, or Custom. Custom opens a calendar: click the first day, then the last day, and it applies and closes. Days in the range are shaded, the ends are solid blue, and days after today and ranges over 366 days are off. Arrow keys move by day and week, Page Up and Page Down by month, Esc closes. The button next to the dropdown shows the dates and reopens the calendar. The range shows next to the title. Export downloads every alert in the range, as an Excel workbook or a CSV file (below). PDF reports come later.

STATUS check-ins are left out of everything on Overview. Overview never shows how long anything took.

**Stat tiles.** Each has an icon and a label, a big number and a context line. The context line is semibold, and its items sit side by side with space between them, no commas: each item has its own icon. Only the word that matters gets a color. When a tile is narrow (a 1280 px screen), Open now shows just the icon and the number per type. Every tile is a button. The big number has a 38 px line height, so the bottom of letters like "g" in "2 min ago" is not cut off.

| Tile | Number | Context line | Click |
|---|---|---|---|
| Open now | Open alerts right now | The open count per type, each with its icon ("1 Medical  1 Suspicious"). Medical and Silent counts are in their type color | Live, Needs action |
| Urgent open | Open MEDICAL plus SILENT alerts. Rose when more than 0 | Up to 2 names, each with its type icon, "+1 more", or "None" | Live, filtered to Medical and Silent |
| Last alert | How long ago the newest alert came in ("12 min ago"), updated every 15 s | The type icon and the student, then a pin icon and the place, or "No alerts yet". The place shortens first when space is tight | Opens that alert |
| Today | Alerts today | "Usually about 2 a day". Orange when today is at least double the usual and at least 3 | Live, All |

"Usually" is the median alerts per day over the days of the range before today. When the range is Today, it is the 7 days before today. Open now, Urgent open and Last alert do not depend on the range.

**Alerts chart.** A stacked area chart: one band per type (Medical at the bottom, then Suspicious, then Silent). The previous period is one thin gray dashed line of the total. Today shows hours instead of days.

- The curves are smooth S-curves through every point (Recharts `bumpX`). They never swing above or below the real counts, unlike some smoothing.
- Each band has a 2 px line in its type color, drawn only where that type has alerts. Lines no longer pile up along zero.
- All bands share one fade, from 42% at the top of the chart to almost nothing at the baseline. Gridlines are faint dashes.
- The chart grows up from the baseline over 0.9 s with one long ease-out, every band and line together, when it first shows and when the range changes. A poll every 30 s does not replay it. Lines keep their width while they grow. No animation with reduced motion.
- Hovering shows a dashed guide line and one dot per type on the hovered day. The dots and the line glide to the next day over 0.26 s instead of jumping, and the tooltip card glides with them. They only ever rest on real days (or hours), never in between: a dot that followed the cursor smoothly would show made-up values like 5.5 alerts at 12:30. A type with no alerts that day has no dot.
- The legend gives each type's count for the range ("Medical 5"). A type with 0 is faded, and it has no band or line in the chart, because there is nothing to draw. That is expected, not a missing color.
- The header says "Alerts" and the count for the range, like "28 in the last 7 days".
- The legend names the periods: Last 7 days and Week before, Last 30 days and 30 days before, Today and Yesterday, This month and Last month, or Selected range and Same length before. When the panel is narrow (at 1280 px) the first word is left out, because the header already says the range. The previous period is always the same number of days just before the range, so "Last month" next to "This month" on the 9th means the 9 days before the 1st.
- Hover the chart: a thin guide line marks the day, and a card shows the date, the total, one row per type and the previous period's count. The card glides from day to day (a 120 ms move) instead of jumping, and flips to the left near the right edge. It does not move with reduced motion.

**Busy hours.** Alerts by hour of day over the range: 24 bars from midnight to 11 PM. Each bar's blue shows how many alerts that hour had, from faint to deep, with a "Fewer to More" scale in the header. When the busiest hour has 6 alerts or fewer, each count has its own shade: 1 is the faintest, 2 a step darker, and so on. With more, the counts are spread over the 6 shades, so the busiest hour is always the deepest. In dark mode the shades go from dim to bright. Hours with no alerts show as short gray dashes. Bar height also follows the count. Hover a bar for the hour and its count; the other bars fade so it stands out. The numbers come from `weekday_hour` in `/api/stats`, added up over the weekdays, STATUS left out.

**Where alerts happened.** A map with every alert in the range that has GPS, as an 8 px dot in its type color. No circles and no clusters. It fits all the dots when the range changes. The mouse wheel zooms only after you click the map. Hover a dot for the type, student, place and time; click it to open the alert. Under the map: "8 indoor alerts are not on the map" (left out when there are none).

**Recent activity.** The 10 newest events in the range, newest first, 40 px each:

- Received: the type icon, then "Medical, Alpha, the courts" (or "Indoors, floor 3").
- Acknowledged: a green check, then "Acknowledged, Alpha's Medical alert".
- Resolved: a gray check, then "Resolved, Alpha's Medical alert".

The time on the right is relative; hover it for the exact time. Click a row to open the alert. Resolving an alert nobody acknowledged sets both times at once, so it shows only as Resolved. "No activity in this range" when empty.

The engineering numbers that used to be on Overview (delivery, rejected messages, Fobs not seen, low battery, reference sensor) are now in Settings > Health. Response flow and Hotspots were removed in version 5.

How each number is worked out:

- Days and hours use the time zone of the computer the server runs on. `/api/stats` says which one in `tz`.
- An alert belongs to the range by the time the server received it. Both ends of the range count: Nov 2 to Nov 8 is 7 days.
- Open now: alerts that are not acknowledged and not resolved, right now, whatever the range.
- An event in Recent activity belongs to the range by its own time (received, acknowledged or resolved).
- The place in tiles, the map and Recent activity is the nearest named place within 200 m ("the bus loop"), "GPS" when there is none that close, "Indoors, floor 3", or nothing.

Every chart has a text summary for screen readers and a hidden table of its numbers. Charts do not animate when the computer asks for reduced motion. The charts use recharts (MIT license). The Overview code loads only when the page is opened, so Live stays fast.

### Live

Three views, picked with the tabs next to the title. The browser remembers the choice.

| View | What you see |
|---|---|
| Split (default) | Alert table on the left, map on the right. Drag the divider between them to give either side more room (the list keeps at least 360 px, the map 320 px). Focus the divider and use Left and Right to move it; double-click it or press Enter on it to put it back in the middle. The browser remembers the position. Under 1024 px wide the table sits above the map |
| List | The alert table, full width |
| Map | The map, edge to edge, with a floating alert list you can hide |

Tools on the right of the title row:

- Filter: one alert type, "Medical and Silent", or all types.
- Search: filters the table by student name or Fob ID.
- Needs action, Acknowledged, All. All also shows resolved alerts, grouped under quiet headers.

Table columns: Type, Student (with the Fob ID), Place, Time, Status, and a narrow column for the row buttons. Status shows only in List view under Acknowledged and All: under Needs action every row is Open, and in Split view the rows are already filtered or grouped by state, so the names get the room instead. In Split view the Fob ID and the place go on a second line under the name.

Rows are calm, with no colored backgrounds:

- 48 px tall with 1 px dividers. The type is a tag: a tinted rectangle with the icon and word in a darker shade of the type color.
- Hover is a light gray. The row buttons, Acknowledge (open alerts only) and Open, appear in their own column at the right end on hover or keyboard focus, so they never cover the time.
- An open MEDICAL or SILENT alert has a small dot in its type color next to the time. It pulses softly, and stays still when the computer asks for reduced motion.
- The row whose alert panel is open, or whose marker you hover on the map, is highlighted. Hovering a row lights up its marker.

Sort order is the same as before: open alerts first, by type (SILENT, MEDICAL, SUSPICIOUS, STATUS), then newest. Then acknowledged, then resolved.

Click a row (or press Enter on it) to open the alert in a large center panel. Esc closes it and focus goes back to the row. The breadcrumb says where it was opened from (Live, Overview or Search). The panel is in sections:

- Header: the student's name, then the type tag, the status and the Fob ID. Acknowledge and Resolve are on the right.
- When and Where: two cards. Pressed shows the time large, with the date and how long ago. Place shows the place in words and Open in Google Maps (or how the floor was found, when there is no GPS). The GPS point and its accuracy are hidden: "Show GPS point" next to Open in Google Maps shows them, and "Hide GPS point" hides them again. They start hidden each time the panel opens.
- Review cameras (SUSPICIOUS only): a plain card with a camera icon in blue. The time window is the large line, with the date, the place and "Within 62 m of the GPS point" under it (no numbers for the point), and Copy for security on the right.
- The map, with the area line under it.
- Timeline: Pressed, Text to duty phone, Acknowledged and Resolved, with their times ("Not yet" until they happen). A filled dot is a step that happened. After Acknowledged, "Help message sent to Fob" with the time, when the server sent the "help is coming" message (WiFi). It means the server sent it, not that the Fob got it.
- Sent late: an alert that reached the server more than 60 s after the press (the Fob's retry queue) gets a small gray "Sent late" tag, next to the time on Live rows and in the device history, with both times in its tooltip. In the panel, the Pressed card shows the Fob's press time with "Arrived ..." under it, and the timeline has Pressed and "Arrived, sent late" as two steps. Needs the Fob's clock (`ts`), so an alert sent with no clock never shows the tag. More than 15 minutes: the tag is yellow and says "Sent late (over 15 min)", and Settings > Health counts it.
- Fob: Battery (number and bar), Link (tag), Floor, Pressure, Temperature, Message number.

The old layout, one list of every property and then the map, is still in the code. In `dashboard/src/components/AlertPeek.jsx`, set `PEEK_LAYOUT` to `"list"` to bring it back.

Copy details (top right) and Copy for security copy two versions at once: the same plain text as before, and a formatted table with a colored title row and a colored status cell. The copied text still has the GPS point, because security needs it. In the Copy for security table, the title row is magenta (#B8246F) and the Review cameras row is a light blue (#E0F0FC fill, #1260A0 text), so the two are easy to tell apart. Excel, Word and email paste the table; a text message or Notepad gets the plain text. This works on http too (the laptop's address on the school WiFi).

### Devices

Under the title, a summary: "4 Fobs, 1 low battery, all seen today". Only the problem part is orange. "Seen today" means a message in the last 24 hours.

One row per registered device: Student, Fob ID, Last seen, Battery, Last start, Link and Open alerts. Last start is from the Fob's boot report (its self-check at power on): how long ago, and "All checks passed" or "2 problems: LoRa radio not answering, GPS not sending data" in orange. "Not reported yet" until a Fob with the new firmware starts. Boot reports never count as alerts or as "seen". Battery is the percent and a thin bar: green at 20% and up, yellow under 20%, red under 10%. Under 20% a bold word in the bar's color follows it, a yellow "Low" or a red "Very low" (plain text, no box), and the percent is semibold too, so the level never depends on color alone. The same battery shows in the alert panel's Fob section. Link is a tag: gray LoRa or slate WiFi. Click a row, or its Open button (in its own column, on hover), to see that device's details and its alert history (newest 200, with a type filter).

The device panel is in sections, like the alert panel:

- Header: the student's name, then "Fob" (or "Reference board"), the link tag and the Fob ID.
- Three cards. Last seen: the time large, the date and how long ago, and the message number under them. Battery: the percent large, a bar, and a bold word in the bar's color (plain text): green "Good", yellow "Low, under 20%" or red "Very low, under 10%". Open alerts: the count, with a teal dot and "Needs action", or "None open".
- Starts and self-checks: Last start (time and how long ago), Why it started ("Power on", "Restarted after a crash" in orange, "Restarted by the watchdog", "Soft reset (Thonny or Ctrl+D)", or "Not reported" for older firmware; the starts table has the same in a Why column, and the Devices page adds ", after a crash" next to Last start), Self-check ("All checks passed" or the failed parts in plain words), WiFi ("WiFi joined" or "No WiFi at start (LoRa still works)", information only, never a failure) and Firmware. Under it, the last 10 starts, newest first.
- Alert history: the table, with the type filter on the right. Pressed shows the date and time with how long ago in gray.

The reference board has no battery or alerts, so it shows Last seen and a Role card ("Ground floor pressure") and no history.

The old device panel, one list of properties and then the history, is still in the code. In `dashboard/src/components/DevicePeek.jsx`, set `DEVICE_LAYOUT` to `"list"` to bring it back.

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
| Ctrl+K | Find a student |
| Ctrl+\ | Open or close the sidebar |
| Up, Down, Enter | Move and open in Find a student, and in an open dropdown |
| Left, Right | Move the Split view divider (when it has focus) |
| Enter | Open the focused row |
| Esc | Close a panel, menu, search or Settings |

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
npm.cmd install           # first time, and after this update (new font packages)
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
- `data.js` also has 4 fake rejected messages and 2 fake duplicates for Settings > Health.
- Delta's acknowledged MEDICAL arrived 21 minutes after the press: "Sent late (over 15 min)" and the yellow Health row.
- Boot reports: `MOCK_BOOTS` in `data.js`. Alpha passed, Bravo's last start had no GPS data, Charlie's had LoRa and pressure failures, Delta has none yet.
- The open SILENT alert from Charlie is "Sent late" (320 s). Acknowledging any alert in mock mode adds "Help message sent to Fob", as if MQTT were on.
- The fake routes are in `dashboard/src/mock/api.js`, including `/api/stats`, `/api/search` and `/api/alerts/<id>`. Export builds both files in the browser from the mock rows. Acknowledge and Resolve work, but only in memory. A page reload starts over.
- A new random alert arrives every 45 seconds, so the sound and auto-zoom can be tested.
- Without a CARTO key the map uses OpenStreetMap tiles (see below to add one).
- The top bar shows a gray "Mock data" tag.

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

- Each alert with GPS gets a 26 px disc in its type color with a 2 px ring and the type icon inside. The icon and ring are white in the light theme and the Midnight page color in the dark theme (a white icon is under 3:1 on the light dark-theme type colors). Acknowledged and resolved markers are smaller (22 px) and faded.
- The hovered or selected alert's marker grows to 1.15 times its size with a stronger shadow. The scale is on the inner element, never on the element Leaflet moves.
- Markers close together merge into a cluster with a count (leaflet.markercluster, MIT license). The ring turns red when an open MEDICAL alert is inside. Click a cluster to zoom in; at the closest zoom it spreads the markers out.
- The control group in the bottom right: zoom in, zoom out, fit all alerts (in the alert panel: center on the alert), and map labels.
- Zoom moves in half steps, and the mouse wheel is a little gentler (`zoomSnap` 0.5, `wheelPxPerZoomLevel` 90). Fit all flies there in 0.5 s, or jumps when the computer asks for reduced motion.
- A poll (every 3 s) never moves the map. The map fits the open alerts once when Live opens, and flies to a new MEDICAL or SUSPICIOUS alert only when Auto-zoom is on.
- "2 alerts have no GPS" in the top left lists the alerts the map cannot show. Click one to open it.

### Circles

Circles show only for the hovered or selected alert (a hovered row or marker, or the alert whose panel is open), so the map stays clean. Every other alert shows only its marker. A circle fades in over 150 ms (no fade with reduced motion). It has a 1.5 px line in the type color and an 8% fill.

Radius is in meters.

- MEDICAL, SILENT, STATUS: radius = `acc`, the GPS accuracy the Fob sends.
- SUSPICIOUS: radius = `acc` + sight radius. This is the area the student could see. It does not grow over time. It is drawn dashed, with a smaller solid circle of radius `acc` inside.

Example: GPS accuracy 12 m and sight radius 50 m gives a 62 m circle. The panel shows "Area: 62 m (GPS 12 m + sight 50 m)".

### Markers and circles move together (fixed in version 4)

Before version 4, markers seemed to stay put while their circles moved, then jumped. The cause was the clustering, not Leaflet's own zoom:

- Circles were drawn on their own, outside the cluster group. A clustered alert still showed its circle, with no marker in the middle (62 of 66 circles in the busiest mock view).
- When zooming changed the clusters, markercluster slid markers into or out of the cluster point for 0.3 s while their circles stayed still. Measured offsets reached 40 to 165 px, then snapped to 0.

Checked and ruled out: no transition or transform on the marker element Leaflet moves (hover effects are on the inner span), no layers recreated on a poll, and markers and circles both follow Leaflet's zoom animation (under 1 px apart for markers that stay on their own).

The fix, in `AlertLayer` (`dashboard/src/components/mapParts.jsx`): one marker and its circles per alert id, kept together and updated in place. Circles live in the overlay pane with the default SVG renderer, markers in the cluster group with `animate: true`. A circle shows only while its marker stands on its own. The Peek map uses the same code for its one alert.

Version 5 keeps these rules and adds one: a circle also needs its alert to be hovered or selected. The headless Edge check was run again on the mock data: it hovered an alert, then zoomed with the buttons and the wheel, dragged the map, used Fit all and waited through polls, measuring every animation frame. It ran on a marker that stays on its own and on one that joins and leaves clusters, with and without reduced motion. Every frame had the marker within about 1 px of its circle's center (largest 1.1 px over all runs), no frame had a circle without its marker, and the circle went away when nothing was hovered. Frames where the alert was zoomed out of view are skipped, because Leaflet does not draw a circle that is off the map.

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

Settings open in a large window from the sidebar (Settings, or the account menu). The window is the same size for every section, min(1100 px, 92% of the width) by min(640 px, 88% of the height), so it never resizes when you switch sections. The list of sections stays put and the right side scrolls inside. Settings are saved in this browser and apply right away. "Search settings" finds rows across all sections.

Every dropdown in the dashboard (Settings, the Overview range, the device history filter) is the app's own: a quiet button that opens a styled list with a check on the current choice. The browser's own list could not be styled. Up, Down, Home and End move, Enter or Space picks, Esc or Tab closes, and Esc closes only the list, not Settings.

| Section | Setting | Choices | Default |
|---|---|---|---|
| Appearance | Theme | Use system setting, Light, Dark | Use system setting |
| Appearance | Time format | 12 h, 24 h | 12 h |
| Appearance | Font (for testing) | Satoshi with General Sans numbers, Satoshi, General Sans, Inter, Geist, IBM Plex Sans, Manrope, DM Sans | Satoshi with General Sans numbers |
| Alerts | Alert sound, with Test sound | on, off | off |
| Alerts | Show STATUS check-ins | on, off | off |
| Map | Auto-zoom to new alerts | on, off | on |
| Map | Map labels | on, off (needs a CARTO key) | on |
| Camera review | Sight radius | 25, 50, 100 m | 50 m, from `/api/config` |
| Camera review | Minutes before, minutes after | 0 to 60 | 2 and 5, from `/api/config` |
| Campus places | Read-only list from `server/places.json` | | |
| Health | System health for a range (below) | Today, Last 7 days, Last 30 days, This month | Last 7 days |
| About | Server version, pressure per floor, map key set (Yes or No), registered devices, Reset to defaults | | |
| About, Testing | Show an empty dashboard (below) | Show empty dashboard, Exit preview | Off |

### Health

Whether the system itself is working. It reads `/api/stats` for the picked range.

| Row | How it is worked out |
|---|---|
| Delivery | Messages received in the range by link, as tags in three grays: LoRa, WiFi, and Unknown (older alerts and test tools). STATUS check-ins are included here, because this row is about the radio path and check-ins use it too |
| Duplicates caught | Exact copies of a message the server already saved (a Fob resending over LoRa or from its retry queue). Acked again, never stored twice, not an attack. See `docs/message-format.md`, "Counters, duplicates and replays" |
| Sent late (over 15 min) | Alerts in the range that reached the server more than 15 minutes after the press. They are accepted and shown, with a yellow "Sent late (over 15 min)" tag. Yellow with a warning icon when there is one or more: a long outage, or a recorded alert played back. Needs the Fob's clock (`ts`) |
| Rejected messages | Messages the server turned away in the range, from the `rejected` table, with the count per reason under it ("3 bad signature, 1 replay"). Red with a warning icon when any are bad signature or replay. Older databases may also list "too old (stale)" from before the counter window, and those count as red too. There is no separate Security page: this row is where security events show |
| Fobs not seen in 24 h | Fobs with no message of any type, STATUS included, in the last 24 hours, with their names. Orange when any |
| Low battery | Fobs whose newest battery reading is under 20%, with names and percents. Orange when any |
| Reference sensor | "Last reading 2 min ago". Orange when there is no reading, or the reading is older than `REF_MAX_AGE_S` (then floors cannot be worked out) |

### Font (for testing)

A temporary dropdown to compare fonts. The default is "Satoshi, General Sans numbers": the app font "SafePing Sans" draws letters in Satoshi and the digits 0 to 9 in General Sans. The choice is saved in this browser (`safeping.fontTest`) and applies right away. Only the picked font's files load. A browser where another font was picked by hand keeps it until the default is picked again.

- "SafePing Sans" is four `@font-face` rules in `src/styles/base.css` with `unicode-range`: Satoshi for every character except U+0030 to U+0039, General Sans for those. All four must declare the same weight range (200 to 900); with different ranges Chrome treats them as separate fonts and never uses the digit faces.
- Satoshi and General Sans are Fontshare files in `dashboard/public/fonts/satoshi/` and `dashboard/public/fonts/general-sans/` (the variable `.woff2` files are used). If a font's files are missing, it shows in the list as "files missing" and cannot be picked.
- Inter, Geist, IBM Plex Sans, Manrope and DM Sans come from the npm packages `@fontsource-variable/inter`, `@fontsource-variable/geist`, `@fontsource-variable/ibm-plex-sans`, `@fontsource-variable/manrope` and `@fontsource-variable/dm-sans` (all SIL Open Font License).
- All the code is in `dashboard/src/components/FontPicker.jsx`. To remove it, delete that file, the `applySavedFont` lines in `src/main.jsx`, the `fontRow` lines in `src/components/SettingsModal.jsx`, and the five packages from `package.json`. Satoshi stays, because its `@font-face` is in `src/styles/base.css`.

### Empty dashboard preview

Settings > About > Testing > "Show empty dashboard" shows SafePing as it looks on its first day: no Fobs, no alerts, no readings. Use it to check that every page still works with no data.

- It applies to this browser tab only (`safeping.emptyPreview` in session storage) and reloads the page. Other tabs and other staff keep the real dashboard. Closing the tab ends it.
- An orange banner across the top says "Empty dashboard preview" and has an Exit preview button. The tab title starts with "(Preview)". Settings shows Exit preview in the same row.
- Real alerts are hidden in this tab, and the alert sound and the Live count stay quiet. Do not leave a preview tab open on the duty laptop.
- It is all in the dashboard (`dashboard/src/lib/preview.js`). The server is not changed and no data is deleted. The dashboard answers its own requests with empty results: no alerts, no devices, no places, no search results, zeros for the stats and a CSV or Excel file with only the header row. `/api/config` still comes from the server. Acknowledge and Resolve do nothing.

What it shows: Overview with 0 in each tile, "No alerts yet" for Last alert and empty states for both charts, the map and Recent activity. Live: "No open alerts. Everything is quiet." with an empty map. Devices: "No devices yet". Find a student: "No students or alerts yet." Health: zeros, and no reference sensor reading.

The alert sound is a short tone made in the browser (no audio files). It plays for new MEDICAL and SUSPICIOUS alerts. Browsers block sound until the page is clicked once. Turning the sound on counts as that click. After a reload, the first click or key press anywhere unlocks it again.

The server version is `VERSION` in `server/app.py` (bump it by hand) plus the git commit the server runs from, when git is available.

## API used by the dashboard

| Route | What it returns |
|---|---|
| `GET /api/alerts` | Alerts. `status=1` adds STATUS, `resolved=1` adds resolved. Each alert also has `place_name`, `place_distance_m` and `place_bearing` (null when there is no named place within 200 m), and `pressed_at` (the Fob's clock, or null), `late_s`, `sent_late` (more than 60 s from press to arrival) and `help_sent_at` (when the help message was sent, or null) |
| `GET /api/alerts/<id>` | One alert, in the same shape, as `{"alert": {...}}`. 404 for an unknown id. New in version 5, for opening older alerts from Overview and search |
| `GET /api/search?q=alpha` | Find a student (below). New in version 5 |
| `POST /api/ack`, `POST /api/resolve` | Body `{"id": 12}`. Acknowledge also sends the Fob the "help is coming" message over MQTT and answers `help_sent` (false with `NO_MQTT=1`) |
| `GET /api/status` | Server time, Reference pressure and age, `last_lora_age_s` |
| `GET /api/config` | `carto_key` (or null), `pa_per_floor`, `ref_max_age_s`, `defaults`, `version`, `commit` |
| `GET /api/devices` | One row per device. Never includes the secret key |
| `GET /api/devices/<id>/alerts` | That device's alerts, all types and states, newest first, up to 200. 404 for an unknown device |
| `GET /api/devices/<id>/boots` | That device's boot reports, newest first, up to 10: `time`, `device_ts`, `counter`, `all_passed`, `failed` (plain words), `wifi`, `firmware`, `link`. `/api/devices` has the newest one as `last_boot` |
| `GET /api/places` | The places from `places.json` |
| `GET /api/stats?from=2026-11-02&to=2026-11-08` | Everything Overview and Settings > Health show, in one answer (below) |
| `GET /api/export.csv?from=2026-11-02&to=2026-11-08` | Every alert in the range as a CSV download (below) |

Every route is behind `require_login`. `from` and `to` are dates (`YYYY-MM-DD`), both included, at most 366 days. A missing or wrong date gets a 400 with `{"ok": false, "error": "..."}` that says what is wrong.

`/api/search` takes `q` (the text typed, up to 100 characters) and `status=1` to include STATUS check-ins. It returns `students`: every Fob (not Reference boards) whose student name or Fob ID contains `q`, any case, sorted by name, each with `device_id`, `student_name` and `last_alert` (`{id, type, time}` of its newest alert, or null). And `alerts`: the newest 8 alerts whose student name or Fob ID contains `q`, in the same shape as `/api/alerts`. With an empty `q` it returns every Fob and the 5 newest alerts. Name matching in the alerts list ignores case for the letters A to Z only (SQLite LIKE).

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
| `open_by_type` | Open alerts right now per type: `MEDICAL`, `SUSPICIOUS`, `SILENT`. New in version 5 |
| `urgent_open` | Open MEDICAL and SILENT alerts right now, newest first: `id`, `name`, `type`. New in version 5 |
| `last_alert` | The newest alert other than STATUS, whatever the range: `id`, `time`, `type`, `name`, `place`. Null when there is none. New in version 5 |
| `today_count` | Alerts today, STATUS left out. New in version 5 |
| `usual_per_day` | The median alerts per day over the days of the range before today, or over the 7 days before today when the range has no such day. New in version 5 |
| `points` | Alerts in the range with GPS: `id`, `type`, `lat`, `lon`, `name`, `place`, `time`, oldest first, at most the newest 2000. New in version 5 |
| `indoor_count` | Alerts in the range with no GPS. New in version 5 |
| `recent_events` | The 10 newest events in the range: `kind` (`received`, `acknowledged` or `resolved`), `time`, `alert_id`, `type`, `name`, `place`. Built from the alert times. New in version 5 |
| `delivery` | `lora`, `wifi`, `unknown`: alerts received in the range by link, STATUS included |
| `duplicates` | Exact resends caught in the range (see Health) |
| `rejected` | `total` and `by_reason` (like `{"bad_signature": 2, "replay": 1}`) for messages rejected in the range |
| `stale_fobs` | Names of Fobs not seen in 24 hours |
| `low_battery_fobs` | `name` and `pct` for each Fob under 20%, lowest first |
| `reference_age_s` | Seconds since the newest Reference reading, or `null` |
| `weekday_hour` | 7 rows (Monday first) of 24 counts (hour 0 to 23), STATUS left out. Busy hours adds up the rows |
| `flow`, `open_now`, `open_medical_now`, `fobs_active`, `fobs_total`, `low_battery`, `median_ack_by_type`, `hotspots` | Still returned, unchanged. The dashboard uses `open_now` only (version 4 used the rest) |

`name` is the student name, or the Fob ID when there is none. `place` is the nearest named place within 200 m, "GPS" when none is that close, "Indoors, floor N", or null.

`/api/export.csv` has one row per alert, oldest first, all types: Received, Type, Student, Fob ID, Status, Place, Floor, Latitude, Longitude, Accuracy (m), Battery (%), Link, Acknowledged, Resolved, Pressed (Fob clock), Sent late ("Yes, 312 s" when it arrived more than 60 s after the press, else empty). The Excel workbook has the same two columns at the end. Times are `YYYY-MM-DD HH:MM:SS` in the server's time zone. Place is the named place ("Near the bus loop"), empty when there is none. The file is named like `safeping-alerts-2026-11-02-to-2026-11-08.csv`. It starts with a byte order mark so Excel reads names correctly, and a cell that starts with `=`, `+`, `-` or `@` gets a leading `'` so a spreadsheet never runs it as a formula.

**Export > Excel workbook** builds a `.xlsx` in the browser from that same CSV (so both files always hold the same rows), with exceljs (MIT license). The library loads only when someone exports. The server is unchanged. The file is named like `safeping-alerts-2026-11-02-to-2026-11-08.xlsx` and has two sheets:

- Summary: the title, the range and the export time. Alerts by type and by status as `COUNTIF` formulas over the Alerts sheet, so they stay right if rows are edited. Then every day of the range with its count per type and a total, busier days in a deeper blue.
- Alerts: one row per alert in an Excel table with filter buttons, banded rows and a frozen header row. Times are real dates (12 h or 24 h, following the Time format setting), coordinates have 6 decimals, and the leading `'` from the CSV is dropped (cells are text, so nothing can run). Type and Status cells are colored like the dashboard tags (Open in teal). Battery is red under 10%, yellow under 20% and green from 20%, like the dashboard. Empty battery cells stay plain.

The CSV export is unchanged. `npm audit` lists a moderate advisory in `uuid`, which exceljs depends on. It does not reach the dashboard: Vite uses the prebuilt browser file of exceljs, and nothing calls `uuid` with a buffer, which is the case the advisory is about.

The Relay item in the top bar uses `last_lora_age_s`. The Relay sends no heartbeat, so it only says when the last LoRa alert arrived. A quiet Relay shows a gray dot, not a fault.

## Database columns

`server/db.py` adds these to the `alerts` table when they are missing (`ALTER TABLE ... ADD COLUMN`). Existing rows keep their data. Versions 2 to 5 added no columns. The acknowledge time was already stored in `acknowledged_at`: Acknowledge sets it, and Resolve sets it too when it is empty.

Rejected messages were already stored: `processor.process()` writes a row to the `rejected` table (`timestamp`, `device_id` when known, `reason`, and the first 300 characters of the message) every time it turns a message away. Version 4 only reads it, and adds an index on its `timestamp` (`CREATE INDEX IF NOT EXISTS`, safe on an old database). No accept or reject decision changed in version 4 or 5.

| Column | Meaning |
|---|---|
| `resolved`, `resolved_at` | Resolve action |
| `link` | `lora` (serial bridge), `wifi` (MQTT) or `unknown` (older alerts, test tools). The dashboard only shows LoRa or WiFi |
| `temperature` | The Fob's `t`, hundredths of a degree C |
| `counter` | The message's `ctr`, shown as "Message number" |

When the Relay starts republishing over MQTT (planned), its alerts will show as WiFi until the Relay path gets its own topic.

New tables (created when missing, safe on an old database): `boot_reports` (the newest 10 per device) and `help_sent` (when a help message was sent for an alert). `accepted_sigs` got a unique index on (device, counter), which the replay and duplicate rule uses. No columns were added to `alerts`: the press time is the existing `device_ts`.

## Login hook

`server/app.py` has a `require_login` decorator on every `/api/*` route and on the dashboard routes, including the two new ones. It lets everything through for now. Login and two-factor go there. They must be checked on the server, not only in the page. The account menu already has a disabled "Log out" for that work. The older optional `DASHBOARD_PASSWORD` check still runs before it.

## Look and colors

Design tokens are in `dashboard/src/styles/tokens.css`, with a light and a dark block. The default font is "SafePing Sans": Satoshi letters with General Sans digits (see Font above). Breadcrumbs ("SafePing / Live", and in the panels) are weight 500. The app uses only these font sizes: 12, 13, 14, 16, 20, 24, 28, 32 px. Panel and section spacing uses 4, 8, 12, 16, 20, 24 and 32 px (tags use 6 px side padding). Numbers use tabular figures everywhere, and big numbers are semibold (600). Content is at most 1600 px wide and centered on every page. In Live Split view the map may use the full width.

Light theme: pure white, the version 4 values (the warm ivory of the first version 5 pass was dropped). Dark theme: Midnight, unchanged from version 4. The sidebar follows the theme: a very light gray in light (no right border), Midnight in dark (with a 1 px border).

| Token | Light (rgb) | Dark (rgb) | Used for |
|---|---|---|---|
| `page`, `surface` | 255,255,255 | 15,16,18 | Page, tables, inputs |
| `sidebar` | 248,248,248 | 11,12,14 | Sidebar, Settings section list |
| `sidebar-hover` | 240,241,242 | 26,27,31 | Sidebar row hover |
| `sidebar-selected` | 234,235,237 | 36,38,43 | Selected sidebar row |
| `surface-raised`, `panel` | 255,255,255 | 22,23,26 | Tiles, chart panels, map controls |
| `surface-overlay` | 255,255,255 | 22,23,26 | Peek, Settings, menus, dropdowns, search |
| `surface-hover` | 240,241,242 | white at 3% | Hover |
| `surface-selected` | 221,222,225 | 36,38,43 | Selected row, tab, segment |
| `border`, `border-raised` | 221,222,225 | 30,32,36 / 38,40,45 | Dividers, gridlines, tile and panel borders |
| `border-bold` | 140,143,151 | 52,55,61 | Chart guide line |
| `text`, `text-subtle`, `text-subtlest` | 30,31,33 / 80,82,88 / 107,110,118 | 237,237,239 / 180,183,190 / 138,143,152 | Text |
| `avatar` | 221,222,225 | 52,55,61 | The "SO" circle (with a 1 px ring) |
| `backdrop` | 5,12,31 at 46%, with a blur | black at 60%, with a blur | Behind Peek, Settings and search |

Types are tags in tables, panels, the map list, the device history and the alert panel: a tinted rectangle, with the icon and word in a darker shade of the type color. Links are tags too, in three grays: a light gray Unknown, a middle gray LoRa and a dark gray WiFi. In legends, Find a student, Recent activity and the Overview tiles, a type is its icon in the type color next to normal text. Status (Open, Acknowledged, Resolved) is a small colored dot and the word in normal text.

| Type | Icon, marker and chart line, light / dark | Tag, light (background / text) | Tag, dark (background / text) |
|---|---|---|---|
| Medical (crimson) | 211,18,58 / 255,107,122 | 255,222,224 / 190,10,51 | 79,9,19 / 255,121,126 |
| Suspicious (LED yellow) | fill 255,195,0 / 255,195,0; lone icon 185,128,0 / 255,195,0 | 255,234,171 / 133,90,0 | 60,43,0 / 255,195,0 |
| Silent (violet) | 122,60,245 / 168,139,250 | 236,229,255 / 106,40,224 | 44,27,85 / 171,148,255 |

Alerts chart bars have their own tokens (`chart-medical`, `chart-suspicious`, `chart-silent`): the type hues at the same weight as the Busy hours blue, so the two charts look like one set. Light 199,74,77 / 229,163,35 / 121,94,201. Dark 216,97,98 / 230,172,61 / 140,119,214. The earlier light bars, which Edwin also liked, were 211,18,58 / 255,195,0 / 122,60,245.
| Status (gray) | 107,110,118 / 150,153,158 | 221,222,225 / 80,82,88 | 36,38,43 / 191,193,196 |
| Unknown link (light gray) | | 240,241,242 / 94,97,105 | 30,31,35 / 150,153,158 |
| LoRa link (middle gray) | | 214,216,220 / 52,54,60 | 48,50,56 / 205,207,211 |
| WiFi link (dark gray) | | 160,164,172 / 20,21,23 | 86,89,97 / 245,245,247 |
| Review cameras (blue), not a type | | 224,240,252 / 18,96,160 | 14,46,66 / 150,215,245 |

Battery colors (`battery-good`, `battery-low`, `battery-critical`, each with a `-text` color for the word; the `-bg` tokens are no longer used):

| Level | Bar, light / dark | Word, light / dark |
|---|---|---|
| Good, 20% and up (green) | 22,163,74 / 74,222,128 | 21,118,58 / 134,239,172 |
| Low, under 20% (yellow) | 234,179,8 / 250,204,21 | 150,96,0 / 253,224,71 |
| Very low, under 10% (red) | 201,55,44 / 248,113,104 | 174,46,36 / 253,152,145 |

The words pass 4.5:1 in both themes, on every background they sit on. The bars are listed as "info" in the contrast check: a yellow that still looks yellow is under 2:1 on white, and the percent and the word next to the bar give the level anyway. Yellow text on white has to be a deep golden yellow to be readable, so the light-theme word is darker than the bar. The "low batteries" count in the Devices summary and in Settings > Health uses the same yellow text.

The type color is used for icons, map markers, map circles, Overview dots and chart bars. Suspicious is the exception for lone icons: they use `type-suspicious-icon`, and the icon inside a yellow marker uses `marker-icon-suspicious` (near black). Red, orange, green and blue keep their status meanings (danger, warning, success, links and buttons), apart from the type colors. Only the Medical and Silent words on Overview tiles are ever colored text.

Suspicious history: amber (199,110,0), deep gold (173,127,10), azure blue (28,142,219), and now magenta, chosen by Edwin: the same pink as the Open dot (214,51,132, dark 244,114,182) and the old Mock data tag. The dataviz palette check is a known fail: magenta is too close to Medical rose (color-blind separation 9.0 passes the target of 8, but normal-vision separation is 9.9, under the 15 floor; in dark 8.4 and 8.4). Types are also told apart by their icons (heart, eye, bell) and words, so nothing depends on color alone. Contrast on white is 4.5:1, so every contrast pair passes.

v6: Suspicious is the Fob LED yellow #FFC300 (255,195,0), chosen by Edwin with the color test in Settings. It looks right in dark. In light the fill is 1.6:1 on white, a known and accepted fail: chart bars, marker discs and map dots are listed as "info" in the contrast check, because they also have an icon, a word and a position. Lone icons in light use a deep amber (185,128,0, 3.4:1), and the tag is a yellow tint with deep amber text (5.1:1). Medical and Silent were made richer in light at the same time (crimson 211,18,58 and violet 122,60,245, both over 5:1 on white). Their dark values did not change.

The Open dot is teal (`--color-open`: light 14,116,144, dark 34,211,238), so it no longer matches the Suspicious pink. The Mock data tag is gray now. The Open status cell in Excel and in Copy details is a light teal (#CFFAFE fill, #0E7490 text).

Link tags are three grays, from light to dark: Unknown, LoRa, WiFi. Review cameras uses a blue tint, a color nothing else has. The Mock data tag is gray. Busy hours is the blue ramp again.

Busy hours shades, `heat-1` to `heat-6`. Light: 211,226,248 / 165,196,240 / 118,162,227 / 74,126,207 / 44,94,178 / 27,64,140. Dark: 36,54,88 / 44,74,124 / 56,98,164 / 78,128,204 / 112,160,232 / 160,196,250. `bar-empty` is 221,222,225 in light and 60,62,67 in dark.

- Icons: Font Awesome 6 Free, solid style. All of them are named in one map, `dashboard/src/lib/icons.js`, so changing an icon is a one-line edit.
- The favicon is a white "S" on a near-black rounded square.

Check contrast after any color change:

```
cd dashboard
npm.cmd run contrast
```

It checks every text and background pair the dashboard uses, in both themes (text 4.5:1, icons and meaningful shapes 3:1). A see-through token (like the dark 3% hover) is checked as it looks on the page, on a tile and on an overlay. Choices made so every pair passes:

- The Live count in the sidebar uses text-subtle, not text-subtlest (text-subtlest is 3.7:1 on the selected row).
- The lighter Busy hours shades are listed as "info": a scale from faint to deep has to start near the background. The bar height, the tooltip and the hidden table give each count, and the deepest shade passes 3:1.
- The Suspicious yellow fill is "info" only. Lone Suspicious icons use the deep amber `type-suspicious-icon` (3.4:1 on white), and the yellow marker has a near-black icon.
- The active row in Find a student uses the hover gray, not surface-selected (a type icon can be under 3:1 on surface-selected in light).
- The Review cameras icon (blue on its tint) is 5.6:1 in light and 9.0:1 in dark.
- Map marker icons in the dark theme use the Midnight page color, not white (white was 1.9:1 to 2.9:1 on the dark-theme type colors).
- The Midnight dark values passed as given. Panel and overlay borders are listed as "info": they separate layers and carry no meaning on their own.

Inputs and dropdown buttons use the quiet 1 px border. Their label identifies them, so they do not need a 3:1 border. Map tile colors in the script are approximate.

## Later

- Phone layout: list-first Live, map behind a button, single-column Overview.
