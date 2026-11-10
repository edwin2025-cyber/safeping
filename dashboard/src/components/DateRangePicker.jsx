import { useEffect, useState } from "react";
import { addDays, dayCount, isoDay, parseDay, rangeText } from "../lib/dates.js";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";
import Popover from "./Popover.jsx";

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];
const MAX_DAYS = 366;

function monthOf(iso) {
  return iso.slice(0, 7);
}

function shiftMonth(ym, n) {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(y, m - 1 + n, 1);
  return isoDay(d).slice(0, 7);
}

/** The weeks of a month as rows of 7 cells: a "YYYY-MM-DD" string, or null for a blank. */
function weeksOf(ym) {
  const [y, m] = ym.split("-").map(Number);
  const lead = new Date(y, m - 1, 1).getDay();
  const count = new Date(y, m, 0).getDate();
  const cells = [...Array(lead).fill(null), ...Array.from({ length: count }, (_, i) => ym + "-" + String(i + 1).padStart(2, "0"))];
  while (cells.length % 7) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7));
}

/** The Custom date range: a button that opens a calendar. Click a start day, then an end day.
    Arrow keys move by day and week, Page Up and Page Down by month, Esc closes. */
export default function DateRangePicker({ from, to, onChange, open, setOpen }) {
  const [anchor, setAnchor] = useState(null);
  const today = isoDay(new Date());
  const [view, setView] = useState(monthOf(to));
  const [pending, setPending] = useState(null);
  const [hover, setHover] = useState(null);
  const [focus, setFocus] = useState(to);

  // Start fresh each time the calendar opens.
  useEffect(() => {
    if (!open) return;
    setView(monthOf(to));
    setFocus(to);
    setPending(null);
    setHover(null);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the keyboard focus on the focused day when it moves.
  useEffect(() => {
    if (!open || !anchor) return;
    const el = document.querySelector('.cal-day[data-day="' + focus + '"]');
    const active = document.activeElement;
    const inside = active === document.body || document.querySelector(".cal")?.contains(active);
    if (el && active !== el && inside) el.focus();
  }, [focus, view, open, anchor]);

  const last = pending ? (hover && hover !== pending ? hover : pending) : to;
  const first = pending || from;
  const lo = first < last ? first : last;
  const hi = first < last ? last : first;

  function pick(day) {
    if (!pending) {
      setPending(day);
      setHover(null);
      return;
    }
    const a = pending < day ? pending : day;
    const b = pending < day ? day : pending;
    onChange(a, b);
    setPending(null);
    setOpen(false);
  }

  function tooLong(day) {
    if (!pending) return false;
    const a = pending < day ? pending : day;
    const b = pending < day ? day : pending;
    return dayCount(a, b) > MAX_DAYS;
  }

  function onGridKey(event) {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
    let next = null;
    if (step) next = addDays(focus, step);
    else if (event.key === "PageUp" || event.key === "PageDown") {
      const d = parseDay(focus);
      d.setMonth(d.getMonth() + (event.key === "PageUp" ? -1 : 1));
      next = isoDay(d);
    } else return;
    event.preventDefault();
    event.stopPropagation();
    if (next > today) next = today;
    setFocus(next);
    setView(monthOf(next));
  }

  const nextDisabled = monthOf(today) <= view;
  const title = parseDay(view + "-01").toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const days = dayCount(from, to);

  return (
    <>
      <button
        ref={setAnchor}
        type="button"
        className="select-btn range-btn"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={"Custom dates: " + rangeText(from, to)}
        onClick={() => setOpen(!open)}
      >
        <Icon icon={icons.calendar} size={13} />
        <span className="num">{rangeText(from, to)}</span>
      </button>
      <Popover anchor={anchor} open={open} onClose={() => setOpen(false)} label="Pick a date range" role="dialog" className="popover--calendar" placement="bottom-end">
        <div className="cal" onMouseLeave={() => setHover(null)}>
          <div className="cal-head">
            <button type="button" className="icon-btn" aria-label="Previous month" onClick={() => setView(shiftMonth(view, -1))}>
              <Icon icon={icons.chevronLeft} size={12} />
            </button>
            <span className="cal-title" aria-live="polite">
              {title}
            </span>
            <button type="button" className="icon-btn" aria-label="Next month" disabled={nextDisabled} onClick={() => setView(shiftMonth(view, 1))}>
              <Icon icon={icons.chevronRight} size={12} />
            </button>
          </div>
          <div className="cal-week" aria-hidden="true">
            {WEEKDAYS.map((w, i) => (
              <span key={i}>{w}</span>
            ))}
          </div>
          <div className="cal-grid" role="grid" aria-label={title} onKeyDown={onGridKey}>
            {weeksOf(view).map((week, wi) => (
              <div className="cal-row" role="row" key={wi}>
                {week.map((day, di) => {
                  if (!day) return <span className="cal-blank" key={di} role="gridcell" />;
                  const off = day > today || tooLong(day);
                  const cls = [
                    "cal-day",
                    day >= lo && day <= hi ? "in-range" : "",
                    day === lo ? "is-start" : "",
                    day === hi ? "is-end" : "",
                    day === today ? "is-today" : "",
                    day === focus ? "is-focus" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <span className="cal-cell" role="gridcell" key={di}>
                      <button
                        type="button"
                        className={cls}
                        data-day={day}
                        data-autofocus={day === focus ? "" : undefined}
                        tabIndex={day === focus ? 0 : -1}
                        disabled={off}
                        aria-label={parseDay(day).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
                        aria-pressed={day >= lo && day <= hi}
                        onClick={() => {
                          setFocus(day);
                          pick(day);
                        }}
                        onMouseEnter={() => pending && setHover(day)}
                      >
                        {Number(day.slice(8))}
                      </button>
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
          <div className="cal-foot">
            {pending ? (
              <span>Now pick the last day</span>
            ) : (
              <span className="num">
                {rangeText(from, to)}, {days} {days === 1 ? "day" : "days"}
              </span>
            )}
          </div>
        </div>
      </Popover>
    </>
  );
}
