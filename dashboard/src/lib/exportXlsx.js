// "Export > Excel workbook": the same rows as the CSV, as a formatted .xlsx built in the browser
// with exceljs (MIT). It loads only when someone exports, so pages stay light.
//
// Sheet "Summary": the range, alerts by type and by status, and alerts per day.
// Sheet "Alerts":  one row per alert in an Excel table (filter buttons, banded rows, frozen
//                  header), real dates and numbers, and colored cells for Type, Status and Battery.
import { fetchCsvText, saveBlob } from "./api.js";
import { addDays, rangeText } from "./dates.js";

const TYPE_WORD = { MEDICAL: "Medical", SUSPICIOUS: "Suspicious", SILENT: "Silent", STATUS: "Status" };
const TYPE_ORDER = ["Medical", "Suspicious", "Silent", "Status"];
const STATUS_ORDER = ["Open", "Acknowledged", "Resolved"];

// Light colors, as ARGB: a tinted fill and a darker word of the same color, like the dashboard tags.
const TYPE_STYLE = {
  Medical: { fill: "FFFFDEE0", font: "FFBE0A33" },
  Suspicious: { fill: "FFFFEAAB", font: "FF855A00" },
  Silent: { fill: "FFECE5FF", font: "FF6A28E0" },
  Status: { fill: "FFDDDEE1", font: "FF505258" },
};
const STATUS_STYLE = {
  Open: { fill: "FFCFFAFE", font: "FF0E7490" },
  Acknowledged: { fill: "FFDCFFF1", font: "FF216E4E" },
  Resolved: { fill: "FFF0F1F2", font: "FF505258" },
};
const HEADER_FILL = "FF1E1F21";

/** A small CSV reader for the server's file: quoted fields, doubled quotes, CRLF. */
export function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else field += c;
  }
  if (field !== "" || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((r) => r.length > 1 || r[0] !== "");
}

/** "2026-11-02 14:03:05" as a Date that Excel shows as that same wall-clock time. */
function excelDate(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/.exec(text || "");
  if (!m) return null;
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
}

/** The CSV puts a ' before text that starts with = + - @ so a spreadsheet never runs it.
    Excel cells here are typed as text, so the ' is not needed. */
function plain(text) {
  return /^'[=+\-@\t\r]/.test(text) ? text.slice(1) : text;
}

function num(text) {
  if (text === "" || text === undefined) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

function solid(argb) {
  return { type: "pattern", pattern: "solid", fgColor: { argb }, bgColor: { argb } };
}

/** Conditional formats that color a column by its word, like the dashboard tags. */
function wordRules(ref, styles) {
  return {
    ref,
    rules: Object.entries(styles).map(([word, s], i) => ({
      type: "containsText",
      operator: "containsText",
      text: word,
      priority: i + 1,
      style: { fill: { type: "pattern", pattern: "solid", bgColor: { argb: s.fill } }, font: { color: { argb: s.font }, bold: true } },
    })),
  };
}

export async function downloadXlsx(from, to, timeFormat) {
  const [mod, csv] = await Promise.all([import("exceljs"), fetchCsvText(from, to)]);
  const ExcelJS = mod.default || mod;
  const rows = parseCsv(csv.replace(/^﻿/, ""));
  rows.shift(); // the header
  const dateFormat = timeFormat === "24" ? "yyyy-mm-dd hh:mm" : "yyyy-mm-dd h:mm AM/PM";

  const data = rows.map((r) => ({
    received: excelDate(r[0]),
    type: TYPE_WORD[r[1]] || r[1],
    student: plain(r[2]),
    fob: plain(r[3]),
    status: r[4],
    place: plain(r[5]),
    floor: num(r[6]),
    lat: num(r[7]),
    lon: num(r[8]),
    accuracy: num(r[9]),
    battery: num(r[10]),
    link: r[11],
    acknowledged: excelDate(r[12]),
    resolved: excelDate(r[13]),
    pressed: excelDate(r[14]),
    late: r[15] || "",
  }));

  const wb = new ExcelJS.Workbook();
  wb.creator = "SafePing";
  wb.created = new Date();
  wb.calcProperties.fullCalcOnLoad = true;

  // ---------- Summary ----------
  const sum = wb.addWorksheet("Summary", { views: [{ showGridLines: false }] });
  sum.columns = [{ width: 22 }, { width: 14 }, { width: 14 }, { width: 14 }, { width: 14 }, { width: 14 }];
  sum.getCell("A1").value = "SafePing alerts";
  sum.getCell("A1").font = { size: 18, bold: true, color: { argb: "FF1E1F21" } };
  sum.getCell("A2").value = rangeText(from, to);
  sum.getCell("A2").font = { size: 12, color: { argb: "FF505258" } };
  sum.getCell("A3").value = "Exported " + new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short", hour12: timeFormat !== "24" });
  sum.getCell("A3").font = { size: 10, color: { argb: "FF6B6E76" } };

  function headerRow(rowNumber, labels) {
    const row = sum.getRow(rowNumber);
    labels.forEach((label, i) => {
      const cell = row.getCell(i + 1);
      cell.value = label;
      cell.font = { bold: true, color: { argb: "FFFFFFFF" } };
      cell.fill = solid(HEADER_FILL);
      cell.alignment = { horizontal: i === 0 ? "left" : "right", vertical: "middle" };
    });
    row.height = 20;
  }
  function line(rowNumber, label, values, style) {
    const row = sum.getRow(rowNumber);
    row.getCell(1).value = label;
    values.forEach((v, i) => {
      row.getCell(i + 2).value = v;
    });
    for (let i = 1; i <= values.length + 1; i++) {
      const cell = row.getCell(i);
      cell.border = { bottom: { style: "thin", color: { argb: "FFDDDEE1" } } };
      if (style) {
        cell.font = { ...(cell.font || {}), ...style.font };
        if (style.fill) cell.fill = style.fill;
      }
    }
    if (style && style.label) {
      row.getCell(1).fill = solid(style.label.fill);
      row.getCell(1).font = { bold: true, color: { argb: style.label.font } };
    }
  }

  // By type: formulas that count the Alerts sheet, so they stay right after edits
  let r = 5;
  headerRow(r, ["By type", "Alerts"]);
  TYPE_ORDER.forEach((t, i) => {
    const count = data.filter((d) => d.type === t).length;
    line(r + 1 + i, t, [{ formula: 'COUNTIF(Alerts!$B:$B,"' + t + '")', result: count }], { label: TYPE_STYLE[t] });
  });
  line(r + 5, "Total", [{ formula: "SUM(B" + (r + 1) + ":B" + (r + 4) + ")", result: data.length }], { font: { bold: true } });

  // By status
  r = 12;
  headerRow(r, ["By status", "Alerts"]);
  STATUS_ORDER.forEach((s, i) => {
    const count = data.filter((d) => d.status === s).length;
    line(r + 1 + i, s, [{ formula: 'COUNTIF(Alerts!$E:$E,"' + s + '")', result: count }], { label: STATUS_STYLE[s] });
  });

  // Per day
  r = 18;
  headerRow(r, ["Day", ...TYPE_ORDER, "Total"]);
  const days = new Map();
  data.forEach((d) => {
    if (!d.received) return;
    const key = d.received.toISOString().slice(0, 10);
    const row = days.get(key) || Object.fromEntries(TYPE_ORDER.map((t) => [t, 0]));
    row[d.type] = (row[d.type] || 0) + 1;
    days.set(key, row);
  });
  // Every day of the range, quiet days included
  const dayKeys = [];
  for (let d = from; d <= to && dayKeys.length < 400; d = addDays(d, 1)) dayKeys.push(d);
  dayKeys.forEach((d) => days.has(d) || days.set(d, Object.fromEntries(TYPE_ORDER.map((t) => [t, 0]))));
  dayKeys.forEach((key, i) => {
    const counts = days.get(key);
    const [y, m, dd] = key.split("-").map(Number);
    const rowNumber = r + 1 + i;
    line(rowNumber, new Date(Date.UTC(y, m - 1, dd)), [...TYPE_ORDER.map((t) => counts[t] || 0), { formula: "SUM(B" + rowNumber + ":E" + rowNumber + ")", result: TYPE_ORDER.reduce((s, t) => s + (counts[t] || 0), 0) }]);
    sum.getRow(rowNumber).getCell(1).numFmt = "ddd, mmm d, yyyy";
  });
  // Busier days get a deeper blue, like Busy hours on Overview
  sum.addConditionalFormatting({
    ref: "F" + (r + 1) + ":F" + (r + dayKeys.length),
    rules: [{ type: "colorScale", priority: 1, cfvo: [{ type: "min" }, { type: "max" }], color: [{ argb: "FFFFFFFF" }, { argb: "FF76A2E3" }] }],
  });
  for (let i = r + 1; i <= r + Math.max(1, dayKeys.length); i++) {
    for (let c = 2; c <= 6; c++) sum.getRow(i).getCell(c).alignment = { horizontal: "right" };
  }

  // ---------- Alerts ----------
  const ws = wb.addWorksheet("Alerts", { views: [{ state: "frozen", ySplit: 1 }] });
  const columns = [
    { name: "Received", width: 20, fmt: dateFormat },
    { name: "Type", width: 13 },
    { name: "Student", width: 26 },
    { name: "Fob ID", width: 16 },
    { name: "Status", width: 15 },
    { name: "Place", width: 34 },
    { name: "Floor", width: 8, fmt: "0" },
    { name: "Latitude", width: 12, fmt: "0.000000" },
    { name: "Longitude", width: 12, fmt: "0.000000" },
    { name: "Accuracy (m)", width: 14, fmt: "0" },
    { name: "Battery (%)", width: 13, fmt: "0" },
    { name: "Link", width: 9 },
    { name: "Acknowledged", width: 20, fmt: dateFormat },
    { name: "Resolved", width: 20, fmt: dateFormat },
    { name: "Pressed (Fob clock)", width: 20, fmt: dateFormat },
    { name: "Sent late", width: 13 },
  ];
  const tableRows = data.map((d) => [
    d.received, d.type, d.student, d.fob, d.status, d.place, d.floor, d.lat, d.lon, d.accuracy, d.battery, d.link, d.acknowledged, d.resolved,
    d.pressed, d.late,
  ]);
  ws.addTable({
    name: "AlertsTable",
    ref: "A1",
    headerRow: true,
    style: { theme: "TableStyleMedium2", showRowStripes: true },
    columns: columns.map((c) => ({ name: c.name, filterButton: true })),
    rows: tableRows.length ? tableRows : [columns.map(() => null)],
  });
  columns.forEach((c, i) => {
    const col = ws.getColumn(i + 1);
    col.width = c.width;
    if (c.fmt) col.numFmt = c.fmt;
  });
  ws.getRow(1).font = { bold: true };
  const last = Math.max(2, tableRows.length + 1);
  ws.addConditionalFormatting(wordRules("B2:B" + last, TYPE_STYLE));
  ws.addConditionalFormatting(wordRules("E2:E" + last, STATUS_STYLE));
  // Battery, like the dashboard: red under 10, yellow under 20, green 20 and up.
  // ISNUMBER keeps empty cells plain (Excel counts an empty cell as 0).
  const batteryRule = (test, priority, fill, font, bold) => ({
    type: "expression",
    formulae: ["AND(ISNUMBER(K2),K2" + test + ")"],
    priority,
    style: { fill: { type: "pattern", pattern: "solid", bgColor: { argb: fill } }, font: { color: { argb: font }, bold } },
  });
  ws.addConditionalFormatting({
    ref: "K2:K" + last,
    rules: [
      batteryRule("<10", 1, "FFFFD5D2", "FFAE2E24", true),
      batteryRule("<20", 2, "FFFEF08A", "FF854D0E", true),
      batteryRule(">=20", 3, "FFDCFCE7", "FF166534", false),
    ],
  });

  const buffer = await wb.xlsx.writeBuffer();
  saveBlob(
    new Blob([buffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
    "safeping-alerts-" + from + "-to-" + to + ".xlsx",
  );
}
