// Formatted versions of "Copy details" and "Copy for security". The clipboard gets these next to
// the plain text (lib/clipboard.js copyRich), so Excel, Word and email paste a tidy two-column
// table with a colored title row. The plain text is unchanged (format.js detailsText, cameraInfo).
// Colors are fixed light values, because pasted documents are usually white.
import { alertState, hasGps, linkMeta, STATES, typeMeta } from "./alertMeta.js";
import { cameraInfo, coords, formatDateTime, googleMapsUrl, placeText } from "./format.js";

// Title rows: the type colors, deep enough for white text. The Review cameras row is a light
// tint of blue, so it stands apart from the magenta Suspicious title.
const TITLE = { MEDICAL: "#C92D3F", SUSPICIOUS: "#B8246F", SILENT: "#744DD6", STATUS: "#6B6E76" };
const CAMERA_ROW = "background:#E0F0FC;color:#1260A0;font-weight:600;";
const STATE_CELL = {
  open: { bg: "#CFFAFE", fg: "#0E7490" },
  acknowledged: { bg: "#DCFFF1", fg: "#216E4E" },
  resolved: { bg: "#F0F1F2", fg: "#505258" },
};
const FONT = "font-family:'Segoe UI',Arial,sans-serif;font-size:13px;";
const LABEL = "padding:6px 12px;border-bottom:1px solid #DDDEE1;color:#505258;font-weight:600;white-space:nowrap;vertical-align:top;";
const VALUE = "padding:6px 12px;border-bottom:1px solid #DDDEE1;color:#1E1F21;";

function esc(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function table(title, color, rows) {
  const body = rows
    .map(([label, html, extra]) => '<tr><td style="' + LABEL + '">' + esc(label) + '</td><td style="' + VALUE + (extra || "") + '">' + html + "</td></tr>")
    .join("");
  return (
    '<table style="border-collapse:collapse;' + FONT + '">' +
    '<tr><th colspan="2" style="padding:8px 12px;background:' + color + ';color:#FFFFFF;font-size:14px;font-weight:600;text-align:left;">' +
    esc(title) +
    "</th></tr>" +
    body +
    "</table>"
  );
}

function studentCell(alert) {
  return esc(alert.student_name || "Unknown") + ' <span style="color:#6B6E76;">(' + esc(alert.device_id) + ")</span>";
}

/** "Copy details" as a table. Same facts as detailsText. */
export function detailsHtml(alert, settings) {
  const type = typeMeta(alert.alert_type);
  const state = alertState(alert);
  const cell = STATE_CELL[state];
  const rows = [
    ["Student", studentCell(alert)],
    ["Pressed", esc(formatDateTime(alert.timestamp, settings.timeFormat))],
    ["Place", esc(placeText(alert) || "Unknown")],
  ];
  if (hasGps(alert)) {
    rows.push(["GPS", esc(coords(alert) + (alert.accuracy !== null ? ", within " + alert.accuracy + " m" : ""))]);
    rows.push(["Map", '<a href="' + esc(googleMapsUrl(alert)) + '">Open in Google Maps</a>']);
  }
  if (alert.battery !== null && alert.battery !== undefined) rows.push(["Battery", esc(alert.battery + "%")]);
  const link = linkMeta(alert.link);
  if (link) rows.push(["Link", esc(link.label)]);
  rows.push(["Status", esc(STATES[state].label), "background:" + cell.bg + ";color:" + cell.fg + ";font-weight:600;"]);
  return table("SafePing " + type.long.toUpperCase() + " alert", TITLE[alert.alert_type] || TITLE.STATUS, rows);
}

/** "Copy for security" as a table. Same facts as cameraInfo(...).text. */
export function cameraHtml(alert, settings) {
  const cam = cameraInfo(alert, settings);
  const rows = [
    ["Student", studentCell(alert)],
    ["Pressed", esc(formatDateTime(alert.timestamp, settings.timeFormat))],
  ];
  if (cam.place) rows.push(["Place", esc(cam.place)]);
  rows.push([
    "Review cameras",
    esc(formatDateTime(cam.start, settings.timeFormat, false) + " to " + formatDateTime(cam.end, settings.timeFormat, false)),
    CAMERA_ROW,
  ]);
  rows.push(["Area", esc(cam.area)]);
  return table("SafePing SUSPICIOUS alert", TITLE.SUSPICIOUS, rows);
}
