# Dashboard v6 changes

All changes are in `dashboard/`. The server did not change.

## Try it

```
cd dashboard
npm.cmd run dev:mock
```

Open the address Vite prints. A new mock alert arrives every 45 s.

## By file

### New files

- `src/lib/clock.js`: one shared 5 s timer (`useNow`). Every relative time and the top bar clock use it. It only runs while something on screen needs it.
- `src/components/SuspiciousColorPicker.jsx`: TEMPORARY. The Suspicious color test in Settings.
- `src/components/suspiciousColor.css`: TEMPORARY. Styles for the color test.
- `src/lib/colorTools.js`: TEMPORARY. Color math for the test: WCAG contrast, OKLab and OKLCH, shade search.

### Changed files

- `src/App.jsx`
  - `nowServer` comes from the shared clock, so times tick on every page with no reload.
  - Passes the newest alert id to Overview, so Overview reloads its stats when a new alert shows up.
  - Keeps the Live sort order and saves it in the browser (`safeping.liveSort`, try/catch).
- `src/lib/alertMeta.js`: `sortAlerts` takes an order. `newest` (default) is newest first inside each group. `urgent` is the old priority order. New `SORT_ORDERS` list.
- `src/components/LivePage.jsx`: new sort button next to the filter, with "Newest first" and "Most urgent first". The pulsing dot for urgent alerts is unchanged.
- `src/lib/icons.js`: added the sort icon.
- `src/components/TopBar.jsx`: the server clock uses the shared clock instead of its own timer.
- `src/components/OverviewPage.jsx`
  - Stats reload every 5 s (was 30 s), and right away when a new alert id appears.
  - Relative times use the shared clock (was a 15 s timer on this page).
  - The Alerts chart is now stacked bars. Bottom up: Medical, Suspicious, Silent. Only the top segment has rounded top corners. 2 px gap between segments. A day with 0 alerts has no bar.
  - Week before: a short dashed tick across each bar, with a halo so it shows on any color. No tick when that total is 0.
  - Y axis: whole numbers only (0, half, top). The top also covers the week-before ticks.
  - Ranges over 35 days show one bar per week. The subtitle then ends with "by week". Today still shows one bar per hour.
  - The grow-in plays only when the chart first shows or the range changes. A refresh does not replay it.
  - The tooltip is the same as before.
- `src/components/overview.css`: bar and tick styles, the hovered slot, the new grow-in rule. Removed the styles for the old hover dots and guide line.
- `src/components/SettingsModal.jsx`: a row can now have a full-width body. Added the color test row.
- `src/components/settings.css`: `.set-row--wide` for that full-width row.
- `src/components/FontPicker.jsx`: its group label changed from "Testing" to "Development", so both test tools sit under one Development heading.
- `src/main.jsx`: applies a saved color test pick on load, like the font test.
- `src/styles/base.css`: `.type-icon--suspicious` reads `--color-type-suspicious-icon` first, then falls back to `--color-type-suspicious`.
- `src/components/map.css`: `.alert-marker--suspicious` reads `--color-marker-icon-suspicious` first, then falls back to `--color-marker-icon`.

`tokens.css` did not change. With no color picked, the dashboard looks exactly as before.

## The Suspicious color test

Settings, Appearance, Development, "Suspicious color (for testing)".

- Drag the square (saturation and brightness) and the hue bar, or type a hex. Arrow keys move both. Shift moves 10 times further.
- "Start from #EBC20C" jumps to the LED yellow.
- From one color it works out, for each theme: fill, text (4.5:1), icon (3:1), tint for type tags, and the icon color inside map markers (white or near black, whichever reads better).
- Shades keep the same hue in OKLCH and only change lightness.
- The difference warning uses OKLab distance (deltaE OK). Under 0.10 is "too close", under 0.15 is "a bit close".
- "Copy values" copies the final variables for both themes, plus the two hardcoded Suspicious colors in `copyHtml.js` and `exportXlsx.js`.
- The pick is saved in the browser (`safeping.suspiciousColorTest`) until "Reset to default".

To remove it later: delete the three TEMPORARY files, then the import and call in `src/main.jsx`, and the import and row in `SettingsModal.jsx`. The two fallbacks in `base.css` and `map.css` can stay. They are needed if you keep a separate icon or marker icon color for Suspicious.

## Round 2: #FFC300 and richer light colors

- `src/styles/tokens.css`
  - Suspicious is #FFC300 in both themes. Light: lone icon 185,128,0, tag 255,234,171 with text 133,90,0, marker icon near black. Dark: tag 60,43,0 with yellow text, marker icon Midnight.
  - New tokens `--color-type-suspicious-icon` and `--color-marker-icon-suspicious` in both themes.
  - Light Medical is richer: 211,18,58, tag 255,222,224 with text 190,10,51.
  - Light Silent is richer: 122,60,245, tag 236,229,255 with text 106,40,224.
  - Dark Medical and Silent did not change.
- `scripts/check-contrast.mjs`: Suspicious icons are checked with the amber icon token. The yellow fill on panels and map tiles is "info", the one accepted fail. The yellow marker is checked with its near-black icon. All pairs pass.
- `src/lib/copyHtml.js`: title colors for Medical, Suspicious (deep amber, so white text reads) and Silent.
- `src/lib/exportXlsx.js`: type cell fill and font colors match the new tags.
- `src/components/SuspiciousColorPicker.jsx`: default is now #FFC300, and its copies of light Medical and Silent are the new values.
- `docs/dashboard.md`: color table and notes.

## Round 3: dark chart bars and brighter dark tags

- `src/styles/tokens.css`
  - New tokens `--color-chart-medical`, `--color-chart-suspicious`, `--color-chart-silent` for the Alerts chart bars. Light: the same as the type colors. Dark: a calmer set with one lightness and saturation (OKLCH 0.70, 0.13): 228,123,124 / 194,152,42 / 161,142,232.
  - Dark Medical tag: 79,9,19 with 255,121,126 (6.0:1). Dark Silent tag: 44,27,85 with 171,148,255 (6.0:1). Deeper tints and brighter words, like the yellow Suspicious tag.
  - Type icons, markers and map dots in dark did not change.
- `src/components/OverviewPage.jsx`: bars use the chart tokens.
- `scripts/check-contrast.mjs`: checks the chart bars on the panel. All pairs pass.

## Round 4: Alerts chart colors tuned like Busy hours

- `src/styles/tokens.css`: the `--color-chart-*` bar colors keep the type hues, at the same weight as the Busy hours blue (OKLCH lightness about 0.57 in light and 0.64 in dark, chroma 0.14 to 0.16; the gold a little lighter so it stays gold).
  - Light: Medical 199,74,77, Suspicious 229,163,35, Silent 121,94,201.
  - Dark: Medical 216,97,98, Suspicious 230,172,61, Silent 140,119,214.
- Saved in case you want them back. Previous light bars: 211,18,58 / 255,195,0 / 122,60,245. Previous dark bars: 228,123,124 / 194,152,42 / 161,142,232.
- Tags, icons, map markers and map dots did not change.

## Round 5: shorter chart legend

- `src/components/OverviewPage.jsx`: the Alerts legend no longer shows "Last 7 days:" (or the other range names) or the "Week before" item. It shows only Medical, Suspicious and Silent with their counts. The dashed week-before ticks on the bars and the "week before" line in the tooltip stay.

## Guesses and open points

- "Development section next to the font picker": I put both tools under one "Development" heading in Appearance and renamed the font picker's group from "Testing".
- The app had one variable for both the Suspicious fill and its icons. A yellow icon on white fails 3:1, so I added two optional variables, `--color-type-suspicious-icon` and `--color-marker-icon-suspicious`. When you make the color permanent, add them to `tokens.css` (Copy values includes them).
- Contrast is measured against the page and panel colors of each theme, and the text also against its tint. The dark theme uses Midnight page `rgb(15, 16, 18)` and panel `rgb(22, 23, 26)`. These and the Medical and Silent colors are copied into the picker file from `tokens.css`.
- The fill is the picked color unchanged in the light theme, as asked. #EBC20C is 1.71:1 on white, so the table shows "Fail" for the fill. Bars and markers still have their icon, word and position. In the dark theme the fill is only lightened if it would be under 3:1.
- There is no Suspicious LED dot in the app today (the pulsing dot is only for Medical and Silent). The preview shows one so you can judge the color.
- Weekly bars start on the first day of the range, not on a Monday. The last week can be shorter.
- The 0.10 threshold is my choice. For reference, today's magenta is 0.099 from Medical.
- `npm.cmd run contrast` still passes. It does not know about the picker values.
- I tested in mock mode with headless Edge screenshots, light and dark: Overview (7 days, Today, 30 days, a custom range of about 4 months), Live and Settings. A new mock alert reached the Last alert tile and Recent activity within about 1 s. Please still check it in a real browser.
