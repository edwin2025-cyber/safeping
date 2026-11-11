import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  usePlotArea,
  useYAxisScale,
  XAxis,
  YAxis,
} from "recharts";
import { MapContainer, useMap } from "react-leaflet";
import L from "../lib/leafletSetup.js";
import { downloadCsv, getJson } from "../lib/api.js";
import { typeMeta } from "../lib/alertMeta.js";
import { dayCount, dayLong, dayTick, hourLong, hourTick, isoDay, parseDay, presetRange, RANGE_PRESETS, rangeText } from "../lib/dates.js";
import { ago, formatDateTime } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import { useReducedMotion } from "../lib/theme.js";
import { hideTooltip, showTooltip } from "../lib/tooltip.js";
import { usePolling } from "../lib/usePolling.js";
import { Select } from "./Controls.jsx";
import DateRangePicker from "./DateRangePicker.jsx";
import Icon from "./Icon.jsx";
import Popover from "./Popover.jsx";
import { TypeIcon } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";
import { AttributionPrefix, BaseTiles, DEFAULT_CENTER, MAP_OPTIONS, MAX_ZOOM, SizeWatcher } from "./mapParts.jsx";

const STATS_MS = 5000; // relative times tick with the shared clock (lib/clock.js)
const RANGE_KEY = "safeping.overviewRange";
const CHART_TYPES = ["MEDICAL", "SUSPICIOUS", "SILENT"]; // STATUS is never in Overview numbers
const URGENT = ["MEDICAL", "SILENT"];
const AXIS = { tickLine: false, axisLine: false, tickMargin: 8, tick: { fontSize: 12, fill: "var(--color-text-subtlest)" } };

// What the chart legend, header and tooltip call this range and the one before it.
const PERIODS = {
  today: { now: "Today", before: "Yesterday", phrase: "today" },
  "7d": { now: "Last 7 days", before: "Week before", phrase: "in the last 7 days" },
  "30d": { now: "Last 30 days", before: "30 days before", phrase: "in the last 30 days" },
  month: { now: "This month", before: "Last month", phrase: "this month" },
  custom: { now: "Selected range", before: "Same length before", phrase: "in the selected range" },
};

// ---------- range ----------

function loadRange() {
  try {
    const saved = JSON.parse(localStorage.getItem(RANGE_KEY) || "{}");
    if (saved.preset === "custom" && parseDay(saved.from) && parseDay(saved.to)) return saved;
    if (RANGE_PRESETS.some((p) => p.value === saved.preset)) return { preset: saved.preset, ...presetRange(saved.preset) };
  } catch {
    // storage blocked or broken: use the default
  }
  return { preset: "7d", ...presetRange("7d") };
}

function saveRange(range) {
  try {
    localStorage.setItem(RANGE_KEY, JSON.stringify(range));
  } catch {
    // ignore
  }
}

function rangeError({ from, to }) {
  if (!parseDay(from) || !parseDay(to)) return "Pick a start and an end date.";
  if (from > to) return "The start date must be on or before the end date.";
  if (dayCount(from, to) > 366) return "Pick at most 366 days.";
  return null;
}

function RangePicker({ range, setRange }) {
  const [calOpen, setCalOpen] = useState(false);
  return (
    <div className="range-picker">
      {range.preset === "custom" && (
        <DateRangePicker
          from={range.from}
          to={range.to}
          open={calOpen}
          setOpen={setCalOpen}
          onChange={(from, to) => setRange({ preset: "custom", from, to })}
        />
      )}
      <Select
        label="Date range"
        align="end"
        value={range.preset}
        options={RANGE_PRESETS}
        onChange={(preset) => {
          setRange(preset === "custom" ? { ...range, preset } : { preset, ...presetRange(preset) });
          setCalOpen(preset === "custom" && range.preset !== "custom");
        }}
      />
    </div>
  );
}

/** Export: an Excel workbook (formatted, with a summary) or the plain CSV. */
function ExportMenu({ from, to, disabled, timeFormat }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const ref = useRef(null);

  async function excel() {
    setOpen(false);
    setBusy(true);
    setFailed(false);
    try {
      const { downloadXlsx } = await import("../lib/exportXlsx.js");
      await downloadXlsx(from, to, timeFormat);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        ref={ref}
        type="button"
        className="btn btn-secondary"
        disabled={disabled || busy}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <Icon icon={icons.download} />
        {busy ? "Preparing" : failed ? "Export failed" : "Export"}
        <Icon icon={icons.chevronDown} size={12} />
      </button>
      <Popover anchor={ref.current} open={open} onClose={() => setOpen(false)} label="Export" placement="bottom-end">
        <div className="popover-title">Every alert in the range</div>
        <button type="button" role="menuitem" className="menu-item" onClick={excel}>
          <Icon icon={icons.excel} fixed />
          <span className="menu-two-line">
            Excel workbook
            <span className="menu-note">Formatted table, colors and a summary sheet</span>
          </span>
        </button>
        <button
          type="button"
          role="menuitem"
          className="menu-item"
          onClick={() => {
            setOpen(false);
            downloadCsv(from, to);
          }}
        >
          <Icon icon={icons.csv} fixed />
          <span className="menu-two-line">
            CSV file
            <span className="menu-note">Plain rows for any program</span>
          </span>
        </button>
      </Popover>
    </>
  );
}

// ---------- small parts ----------

function Panel({ id, icon, title, sub, tools, className = "", children }) {
  return (
    <section className={"panel " + className} aria-labelledby={id + "-title"}>
      <div className="panel-head">
        <div className="panel-head-text">
          <h2 id={id + "-title"} className="panel-title">
            {icon && <Icon icon={icon} className="panel-icon" />}
            {title}
          </h2>
          {sub && <span className="panel-sub num">{sub}</span>}
        </div>
        {tools}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

function PanelEmpty({ icon = icons.chart, text = "No alerts in this range." }) {
  return (
    <div className="panel-empty">
      <Icon icon={icon} />
      <span>{text}</span>
    </div>
  );
}

function Skeleton({ height, width = "100%" }) {
  return <span className="skel" style={{ height, width }} aria-hidden="true" />;
}

function possessive(name) {
  return name + (name.endsWith("s") ? "'" : "'s");
}

// ---------- stat tiles ----------

/** One stat tile: icon and label, big number, a context line. A button when it goes somewhere. */
function Tile({ icon, label, value, valueClass = "", context, contextText, onClick, action }) {
  const body = (
    <>
      <span className="tile-top">
        <Icon icon={icon} fixed />
        <span className="tile-label">{label}</span>
      </span>
      <span className={"tile-value num " + valueClass}>{value}</span>
      <span className="tile-context" title={contextText}>
        {context}
      </span>
    </>
  );
  if (!onClick) return <div className="tile">{body}</div>;
  return (
    <Tooltip label={action}>
      <button type="button" className="tile tile--link" onClick={onClick} aria-label={label + ": " + value + ". " + contextText + ". " + action}>
        {body}
      </button>
    </Tooltip>
  );
}

/** A count and a type word with its icon. Urgent types get their color, the rest stay neutral. */
function TypeCount({ type, n }) {
  const meta = typeMeta(type);
  return (
    <span className="ctx-item">
      <TypeIcon type={type} size={12} />
      <span className={"ctx-text" + (URGENT.includes(type) ? " type-text--" + meta.key : "")}>
        {n}
        <span className="ctx-word"> {meta.label}</span>
      </span>
    </span>
  );
}

/** One item of a context line: an icon and a few words. Items sit side by side with space
    between them, no commas; the icons tell them apart. */
function CtxItem({ icon, type, children, quiet = false }) {
  return (
    <span className={"ctx-item" + (quiet ? " is-quiet" : "")}>
      {type ? <TypeIcon type={type} size={12} /> : <Icon icon={icon} size={12} fixed />}
      <span className="ctx-text">{children}</span>
    </span>
  );
}

function usualText(usual) {
  if (usual === null || usual === undefined) return "No earlier days to compare";
  if (usual === 0) return "Usually none";
  return "Usually about " + Math.max(1, Math.round(usual)) + " a day";
}

function StatTiles({ stats, now, timeFormat, onOpenAlert, goLive }) {
  // 1. Open now
  const byType = stats.open_by_type || {};
  const openParts = CHART_TYPES.filter((t) => byType[t] > 0);
  const openText = openParts.map((t) => byType[t] + " " + typeMeta(t).label).join(", ") || "None open";

  // 2. Urgent open: Medical and Silent
  const urgent = stats.urgent_open || [];
  const shown = urgent.slice(0, 2);
  const more = urgent.length - shown.length;
  const urgentText = urgent.length ? shown.map((u) => u.name).join(", ") + (more ? " and " + more + " more" : "") : "None";

  // 3. Last alert
  const last = stats.last_alert;
  const lastText = last ? [typeMeta(last.type).label, last.name, last.place].filter(Boolean).join(", ") : "No alerts yet";

  // 4. Today
  const usual = stats.usual_per_day;
  const today = stats.today_count;
  const spike = usual !== null && usual !== undefined && today >= 3 && today >= 2 * usual;

  return (
    <div className="tiles" role="group" aria-label="Summary">
      <Tile
        icon={icons.openNow}
        label="Open now"
        value={stats.open_now}
        contextText={openText}
        context={openParts.length ? openParts.map((t) => <TypeCount key={t} type={t} n={byType[t]} />) : <span className="muted">None open</span>}
        onClick={() => goLive({ state: "action", type: "ALL" })}
        action="Go to Live, Needs action"
      />
      <Tile
        icon={icons.urgent}
        label="Urgent open"
        value={urgent.length}
        valueClass={urgent.length ? "type-text--medical" : ""}
        contextText={urgentText}
        context={
          urgent.length ? (
            <>
              {shown.map((u) => (
                <CtxItem key={u.id} type={u.type}>
                  {u.name}
                </CtxItem>
              ))}
              {more > 0 && <span className="ctx-more">+{more} more</span>}
            </>
          ) : (
            <span className="muted">None</span>
          )
        }
        onClick={() => goLive({ state: "action", type: "URGENT" })}
        action="Go to Live, Medical and Silent"
      />
      <Tile
        icon={icons.lastAlert}
        label="Last alert"
        value={last ? ago(now - last.time) : "No alerts yet"}
        valueClass={last ? "" : "is-muted"}
        contextText={last ? lastText + ", " + formatDateTime(last.time, timeFormat, false) : ""}
        context={
          last ? (
            <>
              <CtxItem type={last.type}>{last.name}</CtxItem>
              {last.place && (
                <CtxItem icon={icons.place} quiet>
                  {last.place}
                </CtxItem>
              )}
            </>
          ) : (
            <span className="muted">Nothing received yet</span>
          )
        }
        onClick={last ? () => onOpenAlert(last.id) : null}
        action="Open the alert"
      />
      <Tile
        icon={icons.today}
        label="Today"
        value={today}
        contextText={usualText(usual)}
        context={<span className={spike ? "tone-orange" : undefined}>{usualText(usual)}</span>}
        onClick={() => goLive({ state: "all", type: "ALL" })}
        action="Go to Live, All"
      />
    </div>
  );
}

// ---------- Alerts chart ----------

/** Per-day rows (or per-hour rows for a single day). */
function seriesRows(stats, timeFormat) {
  if (stats.per_hour) {
    return stats.per_hour.map((h) => ({
      tick: hourTick(h.hour, timeFormat),
      title: dayLong(stats.from) + ", " + hourLong(h.hour, timeFormat),
      prevTitle: dayLong(stats.previous_from) + ", " + hourLong(h.hour, timeFormat),
      total: h.count,
      previous: h.previous_count,
      MEDICAL: h.by_type.MEDICAL || 0,
      SUSPICIOUS: h.by_type.SUSPICIOUS || 0,
      SILENT: h.by_type.SILENT || 0,
    }));
  }
  return stats.per_day.map((d) => ({
    tick: dayTick(d.date, stats.days),
    title: dayLong(d.date),
    prevTitle: dayLong(d.previous_date),
    total: d.count,
    previous: d.previous_count,
    MEDICAL: d.by_type.MEDICAL || 0,
    SUSPICIOUS: d.by_type.SUSPICIOUS || 0,
    SILENT: d.by_type.SILENT || 0,
  }));
}

/** Ranges longer than this show one bar per week, so the bars stay readable. */
const WEEKS_AFTER_DAYS = 35;

function byWeek(stats) {
  return stats.days > WEEKS_AFTER_DAYS && !stats.per_hour;
}

/** Per-week rows for long ranges: 7 days per bar from the first day of the range. The last
    bar can be shorter. Same fields as the per-day rows. */
function weekRows(stats) {
  const out = [];
  for (let i = 0; i < stats.per_day.length; i += 7) {
    const days = stats.per_day.slice(i, i + 7);
    const first = days[0];
    const last = days[days.length - 1];
    const sum = (pick) => days.reduce((s, d) => s + pick(d), 0);
    out.push({
      tick: dayTick(first.date, stats.days),
      title: rangeText(first.date, last.date),
      prevTitle: rangeText(first.previous_date, last.previous_date),
      total: sum((d) => d.count),
      previous: sum((d) => d.previous_count),
      MEDICAL: sum((d) => d.by_type.MEDICAL || 0),
      SUSPICIOUS: sum((d) => d.by_type.SUSPICIOUS || 0),
      SILENT: sum((d) => d.by_type.SILENT || 0),
    });
  }
  return out;
}

function tickInterval(stats, rows) {
  if (stats.per_hour) return 5; // 12a, 6a, 12p, 6p
  return rows.length <= 7 ? 0 : "preserveStartEnd";
}

/** Marks the lowest and the highest type with alerts in each bar. The top one gets the
    rounded corners; every segment above the lowest one leaves a small gap under itself. */
function withEnds(rows) {
  return rows.map((r) => {
    const present = CHART_TYPES.filter((t) => r[t] > 0);
    return { ...r, bottom: present[0] || null, top: present[present.length - 1] || null };
  });
}

/** The y axis top: whole numbers only, even, at least 2, and above the week-before ticks too. */
function niceMax(rows) {
  const max = Math.max(0, ...rows.map((r) => Math.max(r.total, r.previous)));
  return Math.max(2, Math.ceil(max / 2) * 2);
}

const BAR_SIDE_GAP = 0.2; // empty space on each side of a bar, as a part of its slot
const BAR_MAX = 40; // px
const SEGMENT_GAP = 2; // px between the colors of one bar
const BAR_RADIUS = 4; // px, top corners of the top segment only

/** A rectangle with only its top corners rounded. */
function topRoundedPath(x, y, w, h, r) {
  if (r <= 0) return "M" + x + "," + y + "h" + w + "v" + h + "h" + -w + "Z";
  return (
    "M" + x + "," + (y + h) +
    "V" + (y + r) +
    "A" + r + "," + r + " 0 0 1 " + (x + r) + "," + y +
    "H" + (x + w - r) +
    "A" + r + "," + r + " 0 0 1 " + (x + w) + "," + (y + r) +
    "V" + (y + h) + "Z"
  );
}

/** Bar colors have their own tokens (--color-chart-*): the type colors in light, a calmer set in dark. */
function chartColor(type) {
  return "var(--color-chart-" + typeMeta(type).key + ")";
}

/** The shape of one type's segment in a bar. Height is its own count. Nothing for a 0. */
function segmentShape(type) {
  return function Segment({ x, y, width, height, payload }) {
    if (!payload || !payload[type] || !(height > 0) || !(width > 0)) return null;
    const h = payload.bottom === type ? height : Math.max(1, height - SEGMENT_GAP);
    const r = payload.top === type ? Math.min(BAR_RADIUS, width / 2, h) : 0;
    return <path className="bar-seg" d={topRoundedPath(x, y, width, h, r)} fill={chartColor(type)} />;
  };
}
const SEGMENT_SHAPES = Object.fromEntries(CHART_TYPES.map((t) => [t, segmentShape(t)]));

/** The legend says how many of each type the range has. A type with none is faded: it has
    no segment in the chart, because there is nothing to draw. */
function Legend({ totals }) {
  return (
    <ul className="ov-legend" aria-hidden="true">
      {CHART_TYPES.map((t) => (
        <li key={t} className={totals[t] ? undefined : "is-zero"} title={totals[t] ? undefined : "No " + typeMeta(t).label + " alerts in this range"}>
          <TypeIcon type={t} size={12} />
          {typeMeta(t).label}
          <span className="ov-legend-count num">{totals[t]}</span>
        </li>
      ))}
    </ul>
  );
}

/** Drawn inside the chart with its own scale: the week-before total of each bar as a short
    dashed tick across it (none when that total is 0). Also tells the CSS where the baseline
    is, so the bars grow up from it when the chart first appears. */
function PrevTicks({ rows, wrapRef }) {
  const plot = usePlotArea();
  const yScale = useYAxisScale();

  useLayoutEffect(() => {
    if (plot && wrapRef.current) wrapRef.current.style.setProperty("--baseline", plot.y + plot.height + "px");
  }, [plot, wrapRef]);

  if (!plot || !yScale || !rows.length) return null;
  const slot = plot.width / rows.length;
  const bar = Math.min(BAR_MAX, slot * (1 - 2 * BAR_SIDE_GAP));
  // A little wider than the bar, so it shows on both sides, but never touching the next tick.
  const tick = bar + Math.min(8, (slot - bar) / 2);
  return (
    <g className="prev-ticks" aria-hidden="true">
      {rows.map((r, i) => {
        if (!(r.previous > 0)) return null;
        const cx = plot.x + (i + 0.5) * slot;
        const y = Math.round(yScale(r.previous)) + 0.5;
        return (
          <g key={i}>
            <line className="prev-tick-halo" x1={cx - tick / 2} x2={cx + tick / 2} y1={y} y2={y} />
            <line className="prev-tick" x1={cx - tick / 2} x2={cx + tick / 2} y1={y} y2={y} />
          </g>
        );
      })}
    </g>
  );
}

/** The tooltip card. It glides between days on the same eased slide as the dots, stays inside
    the panel and flips to the left of the guide line near the right edge. */
function GlideTip({ row, x, wrapRef }) {
  const cardRef = useRef(null);
  const [pos, setPos] = useState({ left: 0, jump: true });
  const shown = row !== null && x !== null;
  const wasShown = useRef(false);

  useLayoutEffect(() => {
    if (!shown || !cardRef.current || !wrapRef.current) {
      wasShown.current = false;
      return;
    }
    const width = wrapRef.current.clientWidth;
    const card = cardRef.current.offsetWidth;
    let left = x + 16;
    if (left + card > width - 4) left = x - 16 - card;
    left = Math.max(4, Math.min(left, width - card - 4));
    setPos({ left, jump: !wasShown.current });
    wasShown.current = true;
  }, [shown, x, row, wrapRef]);

  return (
    <div
      ref={cardRef}
      className={"glide-tip" + (shown ? " is-shown" : "") + (pos.jump ? " is-jump" : "")}
      style={{ transform: "translate(" + Math.round(pos.left) + "px, 8px)" }}
      aria-hidden="true"
    >
      {row && (
        <>
          <div className="glide-tip-title">{row.title}</div>
          <div className="glide-tip-total">
            <span>Total</span>
            <span className="num">{row.total}</span>
          </div>
          {CHART_TYPES.map((t) => (
            <div key={t} className="glide-tip-row">
              <TypeIcon type={t} size={12} />
              <span className="glide-tip-label">{typeMeta(t).label}</span>
              <span className="num">{row[t]}</span>
            </div>
          ))}
          <div className="glide-tip-row glide-tip-prev">
            <span className="legend-line is-dashed" />
            <span className="glide-tip-label">{row.prevTitle}</span>
            <span className="num">{row.previous}</span>
          </div>
        </>
      )}
    </div>
  );
}

function AlertsChart({ stats, rows: plainRows, period, animate }) {
  const wrapRef = useRef(null);
  const [hover, setHover] = useState(null); // { index, x }
  // The bars grow in once: when the chart first shows, or the range changes (the panel
  // remounts then). Refreshes after that only change the numbers.
  const [growing, setGrowing] = useState(true);
  useEffect(() => {
    const timer = setTimeout(() => setGrowing(false), 1100);
    return () => clearTimeout(timer);
  }, []);
  const rows = useMemo(() => withEnds(plainRows), [plainRows]);
  const totals = useMemo(() => Object.fromEntries(CHART_TYPES.map((t) => [t, plainRows.reduce((s, r) => s + r[t], 0)])), [plainRows]);
  const top = niceMax(rows);
  const empty = stats.total === 0 && stats.previous_total === 0;
  const weekly = byWeek(stats);
  const unit = stats.per_hour ? "hour" : weekly ? "week" : "day";
  const sub = stats.total + " " + period.phrase + (weekly ? ", by week" : "");
  const label = "Alerts per " + unit + ", " + stats.total + " " + period.phrase + ". " + period.before + ": " + stats.previous_total + ".";

  function onMove(state) {
    if (!state || !state.isTooltipActive || state.activeTooltipIndex === undefined || state.activeTooltipIndex === null) {
      setHover(null);
      return;
    }
    const index = Number(state.activeTooltipIndex);
    const x = state.activeCoordinate ? state.activeCoordinate.x : null;
    setHover((h) => (h && h.index === index && h.x === x ? h : { index, x }));
  }

  return (
    <Panel id="ov-chart" title="Alerts" sub={sub} tools={!empty && <Legend totals={totals} />} className="ov-chart">
      {empty ? (
        <PanelEmpty />
      ) : (
        <>
          <div role="img" aria-label={label} className={"chart-fill" + (animate && growing ? " is-animated" : "")} ref={wrapRef}>
            {/* Keyed by the range, so the chart starts fresh when the range changes, but not on a poll. */}
            <div className="chart-abs" key={stats.from + "/" + stats.to}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={rows}
                  margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
                  barCategoryGap={BAR_SIDE_GAP * 100 + "%"}
                  maxBarSize={BAR_MAX}
                  accessibilityLayer={false}
                  onMouseMove={onMove}
                  onMouseLeave={() => setHover(null)}
                >
                  <CartesianGrid vertical={false} stroke="var(--color-border)" strokeWidth={1} strokeDasharray="3 4" />
                  <XAxis dataKey="tick" {...AXIS} interval={tickInterval(stats, rows)} minTickGap={12} />
                  <YAxis {...AXIS} width={28} allowDecimals={false} domain={[0, top]} ticks={[0, top / 2, top]} />
                  <ChartTooltip
                    cursor={{ fill: "var(--color-surface-hover)" }}
                    content={() => null}
                    isAnimationActive={false}
                    animationDuration={0}
                    wrapperStyle={{ display: "none" }}
                  />
                  {/* Bottom up: Medical, Suspicious, Silent, the order of the legend */}
                  {CHART_TYPES.map((t) => (
                    <Bar
                      key={t}
                      dataKey={t}
                      name={typeMeta(t).label}
                      stackId="types"
                      fill={chartColor(t)}
                      shape={SEGMENT_SHAPES[t]}
                      activeBar={false}
                      isAnimationActive={false}
                    />
                  ))}
                  <PrevTicks rows={rows} wrapRef={wrapRef} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <GlideTip row={hover ? rows[hover.index] || null : null} x={hover ? hover.x : null} wrapRef={wrapRef} />
          </div>
          <div className="visually-hidden">
            <table>
              <caption>{label}</caption>
              <thead>
                <tr>
                  <th scope="col">{unit === "hour" ? "Hour" : unit === "week" ? "Week" : "Day"}</th>
                  <th scope="col">Alerts</th>
                  {CHART_TYPES.map((t) => (
                    <th key={t} scope="col">
                      {typeMeta(t).label}
                    </th>
                  ))}
                  <th scope="col">{period.before}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.title}>
                    <th scope="row">{r.title}</th>
                    <td>{r.total}</td>
                    {CHART_TYPES.map((t) => (
                      <td key={t}>{r[t]}</td>
                    ))}
                    <td>{r.previous}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}

// ---------- Busy hours ----------

const HEAT_STEPS = 6;

/** The shade of a bar, 1 (faint) to 6 (deep). Up to 6 alerts in the busiest hour, each count
    has its own shade: 1 is the faintest, 2 a bit darker, and so on. Above that, the counts are
    spread over the 6 shades, so the busiest hour is always the deepest. */
function heatStep(n, max) {
  if (n <= 0) return 0;
  if (max <= HEAT_STEPS) return n;
  return Math.max(1, Math.ceil((n / max) * HEAT_STEPS));
}

function HeatScale() {
  return (
    <span className="heat-scale" aria-hidden="true">
      <span>Fewer</span>
      {Array.from({ length: HEAT_STEPS }, (_, i) => (
        <span key={i} className={"heat-swatch heat-" + (i + 1)} />
      ))}
      <span>More</span>
    </span>
  );
}

/** Alerts by hour of day over the range: 24 bars, shaded by how many alerts each hour had,
    empty hours as short gray dashes. STATUS is left out (weekday_hour from /api/stats). */
function BusyHours({ stats, timeFormat }) {
  const hours = Array.from({ length: 24 }, (_, h) => (stats.weekday_hour || []).reduce((sum, day) => sum + (day[h] || 0), 0));
  const max = Math.max(0, ...hours);
  const total = hours.reduce((a, b) => a + b, 0);
  const span = (h) => hourLong(h, timeFormat) + " to " + hourLong((h + 1) % 24, timeFormat);
  const peaks = hours.map((n, h) => (n === max && max > 0 ? h : -1)).filter((h) => h >= 0);
  const label =
    "Alerts by hour of day. " + (peaks.length ? "Busiest: " + peaks.map(span).join(", ") + ", " + max + " alerts." : "No alerts.");
  return (
    <Panel id="ov-busy" title="Busy hours" sub="Alerts by hour of day" tools={total > 0 && <HeatScale />} className="ov-busy">
      {total === 0 ? (
        <PanelEmpty text="No alerts in this range." />
      ) : (
        <>
          <div className="busy" role="img" aria-label={label}>
            <div className="busy-bars">
              {hours.map((n, h) => (
                <span
                  key={h}
                  className="busy-col"
                  onMouseEnter={(e) =>
                    showTooltip(e.currentTarget, { label: span(h), shortcut: n + (n === 1 ? " alert" : " alerts") + (n === max ? ", the busiest" : "") }, 0)
                  }
                  onMouseLeave={() => hideTooltip()}
                >
                  <span
                    className={"busy-bar" + (n === 0 ? " is-empty" : " heat-" + heatStep(n, max))}
                    style={n ? { height: Math.max(4, (n / max) * 92) + "%" } : undefined}
                  />
                </span>
              ))}
            </div>
            <div className="busy-axis" aria-hidden="true">
              {[0, 6, 12, 18].map((h) => (
                <span key={h} style={{ left: ((h + 0.5) / 24) * 100 + "%" }}>
                  {hourTick(h, timeFormat)}
                </span>
              ))}
            </div>
          </div>
          <div className="visually-hidden">
            <table>
              <caption>{label}</caption>
              <thead>
                <tr>
                  <th scope="col">Hour</th>
                  <th scope="col">Alerts</th>
                </tr>
              </thead>
              <tbody>
                {hours.map((n, h) => (
                  <tr key={h}>
                    <th scope="row">{span(h)}</th>
                    <td>{n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}

// ---------- Where alerts happened ----------

/** Scroll-wheel zoom stays off until the map is clicked, and turns off again when the pointer leaves. */
function WheelAfterClick() {
  const map = useMap();
  useEffect(() => {
    const on = () => map.scrollWheelZoom.enable();
    const off = () => map.scrollWheelZoom.disable();
    map.on("click", on);
    map.on("mouseout", off);
    return () => {
      map.off("click", on);
      map.off("mouseout", off);
    };
  }, [map]);
  return null;
}

/** One 8 px dot per alert with GPS, in its type color at 75%. No circles, no clustering.
    Fits all dots when the range changes, not on every poll. */
function DotLayer({ points, fitKey, onOpen, timeFormat }) {
  const map = useMap();
  const groupRef = useRef(null);
  const fitted = useRef(null);
  const handlers = useRef({ onOpen });
  handlers.current = { onOpen };
  const sig = points.map((p) => p.id + ":" + p.type).join(",");

  useEffect(() => {
    const group = L.featureGroup().addTo(map);
    groupRef.current = group;
    return () => {
      map.removeLayer(group);
      groupRef.current = null;
    };
  }, [map]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    group.clearLayers();
    points.forEach((p) => {
      const meta = typeMeta(p.type);
      const dot = L.circleMarker([p.lat, p.lon], {
        radius: 4,
        weight: 1,
        opacity: 1,
        fillOpacity: 0.75,
        className: "ov-dot ov-dot--" + meta.key,
        bubblingMouseEvents: false,
      });
      dot.on("mouseover", () => {
        const el = dot.getElement();
        const where = p.place ? p.place + ", " : "";
        if (el) showTooltip(el, { label: meta.label + ", " + p.name, shortcut: where + formatDateTime(p.time, timeFormat, false) }, 0);
      });
      dot.on("mouseout", () => hideTooltip());
      dot.on("click", () => {
        hideTooltip();
        handlers.current.onOpen(p.id);
      });
      dot.addTo(group);
    });
    if (fitted.current !== fitKey && points.length) {
      fitted.current = fitKey;
      map.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lon])), { padding: [20, 20], maxZoom: 17, animate: false });
    }
    // sig stands for points: redraw only when the dots change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, fitKey, map, timeFormat]);

  return null;
}

function PlacesPanel({ stats, fitKey, theme, settings, cartoKey, configLoaded, timeFormat, onOpenAlert }) {
  const points = stats.points || [];
  const indoor = stats.indoor_count || 0;
  const reducedMotion = useReducedMotion();
  return (
    <Panel id="ov-map" icon={icons.map} title="Where alerts happened" className="ov-map">
      {points.length === 0 ? (
        <PanelEmpty icon={icons.map} text="No alerts with GPS in this range." />
      ) : (
        <div className="map-wrap ov-map-wrap">
          <MapContainer
            center={DEFAULT_CENTER}
            zoom={16}
            maxZoom={MAX_ZOOM}
            {...MAP_OPTIONS}
            scrollWheelZoom={false}
            className="map"
            zoomAnimation={!reducedMotion}
            fadeAnimation={!reducedMotion}
            markerZoomAnimation={!reducedMotion}
          >
            {configLoaded && <BaseTiles theme={theme} labels={settings.mapLabels} cartoKey={cartoKey} />}
            <AttributionPrefix />
            <SizeWatcher />
            <WheelAfterClick />
            <DotLayer points={points} fitKey={fitKey} onOpen={onOpenAlert} timeFormat={timeFormat} />
          </MapContainer>
        </div>
      )}
      {indoor > 0 && (
        <p className="panel-note panel-foot num">
          {indoor} indoor {indoor === 1 ? "alert is" : "alerts are"} not on the map
        </p>
      )}
    </Panel>
  );
}

// ---------- Recent activity ----------

function eventText(e) {
  const type = typeMeta(e.type).label;
  if (e.kind === "acknowledged") return "Acknowledged, " + possessive(e.name) + " " + type + " alert";
  if (e.kind === "resolved") return "Resolved, " + possessive(e.name) + " " + type + " alert";
  return [type, e.name, e.place].filter(Boolean).join(", ");
}

function EventIcon({ e }) {
  if (e.kind === "acknowledged") return <Icon icon={icons.acknowledged} size={14} fixed className="feed-ack" />;
  if (e.kind === "resolved") return <Icon icon={icons.resolve} size={14} fixed className="feed-resolved" />;
  return <TypeIcon type={e.type} size={14} />;
}

function ActivityPanel({ stats, now, timeFormat, onOpenAlert }) {
  const events = stats.recent_events || [];
  return (
    <Panel id="ov-feed" icon={icons.activity} title="Recent activity" className="ov-feed">
      {events.length === 0 ? (
        <PanelEmpty icon={icons.activity} text="No activity in this range" />
      ) : (
        <ol className="feed">
          {events.map((e) => {
            const text = eventText(e);
            const when = formatDateTime(e.time, timeFormat, false);
            return (
              <li key={e.kind + e.alert_id}>
                <button type="button" className="feed-row" onClick={() => onOpenAlert(e.alert_id)} aria-label={text + ", " + when + ". Open the alert"}>
                  <EventIcon e={e} />
                  <span className="feed-text">{text}</span>
                  <Tooltip label={when}>
                    <span className="feed-time num">{ago(now - e.time)}</span>
                  </Tooltip>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}

// ---------- loading ----------

function LoadingPanels() {
  return (
    <>
      <div className="tiles" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="tile">
            <Skeleton height={16} width={96} />
            <Skeleton height={32} width={64} />
            <Skeleton height={16} width={140} />
          </div>
        ))}
      </div>
      {["ov-chart", "ov-busy", "ov-map", "ov-feed"].map((c) => (
        <section key={c} className={"panel " + c} aria-hidden="true">
          <Skeleton height={16} width={120} />
          <div className="panel-body skel-gap">
            <Skeleton height="100%" />
          </div>
        </section>
      ))}
    </>
  );
}

// ---------- page ----------

export default function OverviewPage({ timeFormat, nowServer, latestAlertId, theme, settings, cartoKey, configLoaded, onOpenAlert, goLive }) {
  const [range, setRangeState] = useState(loadRange);
  const setRange = (next) => {
    setRangeState(next);
    saveRange(next);
  };
  const error = rangeError(range);
  const key = range.from + "/" + range.to;
  const sub = error ? "" : rangeText(range.from, range.to);
  const period = PERIODS[range.preset] || PERIODS.custom;

  const [result, setResult] = useState(null); // { key, stats }
  const [failed, setFailed] = useState(false);
  const seq = useRef(0);
  // Every 5 s while Overview is open, and right away when the alerts poll sees a new alert id
  // (latestAlertId in the deps restarts the timer with an immediate load).
  usePolling(
    () => {
      const n = ++seq.current;
      getJson("/api/stats?from=" + range.from + "&to=" + range.to)
        .then((stats) => {
          if (n !== seq.current) return;
          setResult({ key, stats });
          setFailed(false);
        })
        .catch(() => n === seq.current && setFailed(true));
    },
    STATS_MS,
    !error,
    [key, latestAlertId],
  );

  const reduced = useReducedMotion();
  const now = nowServer; // the shared clock in App (lib/clock.js)
  const stats = result && result.key === key ? result.stats : null;
  const rows = useMemo(() => (stats ? (byWeek(stats) ? weekRows(stats) : seriesRows(stats, timeFormat)) : []), [stats, timeFormat]);

  return (
    <div className="page page--overview">
      <header className="page-header ov-header">
        <div className="ov-head-text">
          <h1 className="page-title">Overview</h1>
          <p className="page-sub num">{error ? "No range picked" : sub}</p>
        </div>
        <div className="view-tools">
          <RangePicker range={range} setRange={setRange} />
          {/* PDF reports come later. Export downloads every alert in the range. */}
          <ExportMenu from={range.from} to={range.to} disabled={!!error} timeFormat={timeFormat} />
        </div>
      </header>
      <div className="overview-scroll">
        {error && (
          <p className="range-error" role="alert">
            {error}
          </p>
        )}
        {!error && failed && !stats && <p className="range-error">Waiting for the server.</p>}
        {!error && (
          <div className="overview">
            {stats ? (
              <>
                <StatTiles stats={stats} now={now} timeFormat={timeFormat} onOpenAlert={onOpenAlert} goLive={goLive} />
                <AlertsChart stats={stats} rows={rows} period={period} animate={!reduced} />
                <BusyHours stats={stats} timeFormat={timeFormat} />
                <PlacesPanel
                  stats={stats}
                  fitKey={key}
                  theme={theme}
                  settings={settings}
                  cartoKey={cartoKey}
                  configLoaded={configLoaded}
                  timeFormat={timeFormat}
                  onOpenAlert={onOpenAlert}
                />
                <ActivityPanel stats={stats} now={now} timeFormat={timeFormat} onOpenAlert={onOpenAlert} />
              </>
            ) : (
              <LoadingPanels />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
