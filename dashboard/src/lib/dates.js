// Day ranges for Overview. A day is a "YYYY-MM-DD" string in local time.
// Both ends of a range are included: Nov 2 to Nov 8 is 7 days.

export function isoDay(date) {
  return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
}

/** A Date at local midnight, or null when the text is not a real day (2026-02-31). */
export function parseDay(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return null;
  const date = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return isoDay(date) === iso ? date : null;
}

export function addDays(iso, n) {
  const date = parseDay(iso);
  date.setDate(date.getDate() + n);
  return isoDay(date);
}

/** Number of days from one day to another, both included. */
export function dayCount(fromIso, toIso) {
  const a = parseDay(fromIso);
  const b = parseDay(toIso);
  const utc = (d) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.round((utc(b) - utc(a)) / 86400000) + 1;
}

export const RANGE_PRESETS = [
  { value: "today", label: "Today" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "month", label: "This month" },
  { value: "custom", label: "Custom" },
];

/** { from, to } for a preset, ending today. */
export function presetRange(preset, now = new Date()) {
  const today = isoDay(now);
  if (preset === "today") return { from: today, to: today };
  if (preset === "30d") return { from: addDays(today, -29), to: today };
  if (preset === "month") return { from: today.slice(0, 8) + "01", to: today };
  return { from: addDays(today, -6), to: today };
}

const SHORT = { month: "short", day: "numeric" };
const LONG = { month: "short", day: "numeric", year: "numeric" };

/** "Nov 2 to Nov 8, 2026", "Dec 28, 2025 to Jan 3, 2026" or "Nov 9, 2026". */
export function rangeText(fromIso, toIso) {
  const a = parseDay(fromIso);
  const b = parseDay(toIso);
  if (fromIso === toIso) return a.toLocaleDateString(undefined, LONG);
  const first = a.getFullYear() === b.getFullYear() ? a.toLocaleDateString(undefined, SHORT) : a.toLocaleDateString(undefined, LONG);
  return first + " to " + b.toLocaleDateString(undefined, LONG);
}

/** Axis label: "Mon" for a week or less, "Nov 2" for longer ranges. */
export function dayTick(iso, days) {
  const d = parseDay(iso);
  return days <= 7 ? d.toLocaleDateString(undefined, { weekday: "short" }) : d.toLocaleDateString(undefined, SHORT);
}

/** "Mon, Nov 2" */
export function dayLong(iso) {
  return parseDay(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

/** Short hour for axes: "12a", "6a", "12p" (12 h) or "00", "06", "12" (24 h). */
export function hourTick(hour, timeFormat) {
  if (timeFormat === "24") return String(hour).padStart(2, "0");
  const h = hour % 12 === 0 ? 12 : hour % 12;
  return h + (hour < 12 ? "a" : "p");
}

/** Hour for tooltips: "3 PM" or "15:00". */
export function hourLong(hour, timeFormat) {
  if (timeFormat === "24") return String(hour).padStart(2, "0") + ":00";
  const h = hour % 12 === 0 ? 12 : hour % 12;
  return h + (hour < 12 ? " AM" : " PM");
}
