import { useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, BarChart3, Download } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ComposedChart, Line, LineChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from "recharts";
import { downloadCsv, getJson } from "../lib/api.js";
import { TYPE_ORDER, typeMeta } from "../lib/alertMeta.js";
import { dayCount, dayLong, dayTick, hourLong, hourTick, isoDay, parseDay, presetRange, RANGE_PRESETS, rangeText } from "../lib/dates.js";
import { formatDuration } from "../lib/format.js";
import { useReducedMotion } from "../lib/theme.js";
import { hideTooltip, showTooltip } from "../lib/tooltip.js";
import { usePolling } from "../lib/usePolling.js";
import { Select, Switch } from "./Controls.jsx";
import { TypeTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";

const ICON = { size: 16, strokeWidth: 1.75, "aria-hidden": true };
const STATS_MS = 30000;
const RANGE_KEY = "safeping.overviewRange";
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const LINE_COLOR = {
  MEDICAL: "var(--color-red-bold)",
  SUSPICIOUS: "var(--color-chart-yellow)",
  SILENT: "var(--color-purple-bold)",
  STATUS: "var(--color-gray-bold)",
};
const AXIS = { tickLine: false, axisLine: false, tickMargin: 8, tick: { fontSize: 12, fill: "var(--color-text-subtlest)" } };
const CURSOR = { stroke: "var(--color-border-bold)", strokeWidth: 1 };

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
  const today = isoDay(new Date());
  return (
    <div className="range-picker">
      {range.preset === "custom" && (
        <>
          <input
            type="date"
            className="input range-date"
            aria-label="Start date"
            value={range.from}
            max={today}
            onChange={(e) => setRange({ ...range, from: e.target.value })}
          />
          <span className="range-to">to</span>
          <input
            type="date"
            className="input range-date"
            aria-label="End date"
            value={range.to}
            max={today}
            onChange={(e) => setRange({ ...range, to: e.target.value })}
          />
        </>
      )}
      <Select
        label="Date range"
        value={range.preset}
        options={RANGE_PRESETS}
        onChange={(preset) => setRange(preset === "custom" ? { ...range, preset } : { preset, ...presetRange(preset) })}
      />
    </div>
  );
}

// ---------- small parts ----------

function Panel({ id, title, sub, tools, className = "", children }) {
  return (
    <section className={"panel " + className} aria-labelledby={id + "-title"}>
      <div className="panel-head">
        <div className="panel-head-text">
          <h2 id={id + "-title"} className="panel-title">
            {title}
          </h2>
          {sub && <p className="panel-sub">{sub}</p>}
        </div>
        {tools}
      </div>
      {children}
    </section>
  );
}

function PanelEmpty({ text = "No alerts in this range" }) {
  return (
    <div className="panel-empty">
      <BarChart3 {...ICON} />
      <span>{text}</span>
    </div>
  );
}

function Skeleton({ height, width = "100%" }) {
  return <span className="skel" style={{ height, width }} aria-hidden="true" />;
}

/** Tooltip box for the charts, styled like the app tooltip. */
function TipBox({ title, rows }) {
  return (
    <div className="chart-tip">
      <div className="chart-tip-title">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="chart-tip-row">
          <span className={"chart-tip-key" + (r.dashed ? " is-dashed" : "")} style={{ "--key": r.color }} aria-hidden="true" />
          <span className="chart-tip-label">{r.label}</span>
          <span className="chart-tip-value">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

function plural(n, word) {
  return n + " " + word + (n === 1 ? "" : "s");
}

/** Per-day rows (or per-hour rows for a single day) for the line charts. */
function seriesRows(stats, timeFormat) {
  if (stats.per_hour) {
    return stats.per_hour.map((h) => ({
      tick: hourTick(h.hour, timeFormat),
      title: dayLong(stats.from) + ", " + hourLong(h.hour, timeFormat),
      prevTitle: dayLong(stats.previous_from) + ", " + hourLong(h.hour, timeFormat),
      current: h.count,
      previous: h.previous_count,
      ...h.by_type,
    }));
  }
  return stats.per_day.map((d) => ({
    tick: dayTick(d.date, stats.days),
    title: dayLong(d.date),
    prevTitle: dayLong(d.previous_date),
    current: d.count,
    previous: d.previous_count,
    ...d.by_type,
  }));
}

function tickInterval(stats) {
  if (stats.per_hour) return 5; // 12a, 6a, 12p, 6p
  return stats.days <= 7 ? 0 : "preserveStartEnd";
}

function periodWord(days) {
  return days === 1 ? "the day before" : "previous " + days + " days";
}

// ---------- Alerts ----------

function changeLine(total, previous, days) {
  if (previous === 0) return { tone: "flat", text: "No alerts in the previous period" };
  if (total === previous) return { tone: "flat", text: "Same as " + periodWord(days) };
  const pct = Math.round((Math.abs(total - previous) / previous) * 100);
  // More alerts is worse, so up is red and down is green.
  return total > previous
    ? { tone: "up", Icon: ArrowUp, text: "Up " + pct + "% vs " + periodWord(days) }
    : { tone: "down", Icon: ArrowDown, text: "Down " + pct + "% vs " + periodWord(days) };
}

function AlertsPanel({ stats, rows, sub, animate }) {
  const change = changeLine(stats.total, stats.previous_total, stats.days);
  const empty = stats.total === 0 && stats.previous_total === 0;
  const unit = stats.per_hour ? "hour" : "day";
  const label =
    "Alerts per " + unit + ", " + sub + ", " + stats.total + " total. " + "Previous period: " + stats.previous_total + ".";
  return (
    <Panel id="ov-alerts" title="Alerts" sub={sub} className="ov-span-7">
      <div className="alerts-body">
        <div className="alerts-figure">
          <p className="big-number">{stats.total}</p>
          <p className={"change change--" + change.tone}>
            {change.Icon && <change.Icon size={14} strokeWidth={2} aria-hidden="true" />}
            {change.text}
          </p>
          {!empty && (
            <ul className="mini-legend" aria-hidden="true">
              <li>
                <span className="legend-line" style={{ "--key": "var(--color-blue-bold)" }} />
                This period
              </li>
              <li>
                <span className="legend-line is-dashed" style={{ "--key": "var(--color-gray-bold)" }} />
                {periodWord(stats.days).replace(/^./, (c) => c.toUpperCase())}
              </li>
            </ul>
          )}
        </div>
        {empty ? (
          <PanelEmpty />
        ) : (
          <div className="alerts-chart">
            <div role="img" aria-label={label} className="chart-box">
              <ResponsiveContainer width="100%" height={168}>
                <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }} accessibilityLayer={false}>
                  <XAxis dataKey="tick" {...AXIS} padding={{ left: 12, right: 12 }} interval={tickInterval(stats)} minTickGap={12} />
                  <YAxis hide allowDecimals={false} domain={[0, (max) => Math.max(1, max)]} />
                  <ChartTooltip
                    cursor={CURSOR}
                    isAnimationActive={false}
                    wrapperStyle={{ outline: "none" }}
                    content={({ active, payload }) =>
                      active && payload && payload.length ? (
                        <TipBox
                          title={payload[0].payload.title}
                          rows={[
                            { label: "This period", value: payload[0].payload.current, color: "var(--color-blue-bold)" },
                            { label: payload[0].payload.prevTitle, value: payload[0].payload.previous, color: "var(--color-gray-bold)", dashed: true },
                          ]}
                        />
                      ) : null
                    }
                  />
                  <Line
                    type="monotone"
                    dataKey="previous"
                    stroke="var(--color-gray-bold)"
                    strokeWidth={1.5}
                    strokeDasharray="4 4"
                    dot={false}
                    activeDot={false}
                    isAnimationActive={animate}
                  />
                  <Area
                    type="monotone"
                    dataKey="current"
                    stroke="var(--color-blue-bold)"
                    strokeWidth={2}
                    fill="var(--color-blue-bold)"
                    fillOpacity={0.1}
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--color-panel)", fill: "var(--color-blue-bold)" }}
                    isAnimationActive={animate}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="visually-hidden"><table>
              <caption>{label}</caption>
              <thead>
                <tr>
                  <th scope="col">{unit === "hour" ? "Hour" : "Day"}</th>
                  <th scope="col">Alerts</th>
                  <th scope="col">Previous period</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.title}>
                    <th scope="row">{r.title}</th>
                    <td>{r.current}</td>
                    <td>{r.previous}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </div>
        )}
      </div>
    </Panel>
  );
}

// ---------- Summary ----------

function Stat({ value, label, tone, href, accent, muted }) {
  const body = (
    <>
      <span className={"stat-value" + (tone ? " stat-value--" + tone : "") + (muted ? " stat-value--muted" : "")}>{value}</span>
      <span className={"stat-bar" + (accent ? " is-accent" : "")} aria-hidden="true" />
      <span className="stat-label">{label}</span>
    </>
  );
  if (!href) return <div className="stat">{body}</div>;
  const where = href === "#/live" ? "Live" : "Devices";
  return (
    <Tooltip label={"Go to " + where}>
      <a className="stat stat--link" href={href} aria-label={label + ": " + value + ". Go to " + where}>
        {body}
      </a>
    </Tooltip>
  );
}

function SummaryPanel({ stats, sub }) {
  const median = stats.flow.median_ack_s;
  return (
    <Panel id="ov-summary" title="Summary" sub={sub} className="ov-span-5">
      <div className="stats">
        <Stat value={median === null ? "No data" : formatDuration(median)} muted={median === null} label="Median time to acknowledge" accent />
        <Stat value={stats.open_now} label="Open now" tone={stats.open_medical_now > 0 ? "red" : null} href="#/live" />
        <Stat value={stats.fobs_active + " of " + stats.fobs_total} label="Fobs active" href="#/devices" />
        <Stat value={stats.low_battery} label="Low battery" tone={stats.low_battery > 0 ? "orange" : null} href="#/devices" />
      </div>
    </Panel>
  );
}

// ---------- Response flow ----------

const FLOW_W = 0.16; // half the width of the curve between two steps
const smooth = (t) => t * t * (3 - 2 * t);

/** Points for three flat blocks joined by smooth curves. x runs 0 to 3, one unit per step.
    Each step is its own series so each block gets its own color. */
function flowPoints(counts) {
  const xs = [0];
  for (const b of [1, 2]) {
    for (let i = 0; i <= 12; i++) xs.push(b - FLOW_W + (2 * FLOW_W * i) / 12);
  }
  xs.push(3);
  const value = (x) => {
    for (const b of [1, 2]) {
      if (Math.abs(x - b) <= FLOW_W) return counts[b - 1] + (counts[b] - counts[b - 1]) * smooth((x - (b - FLOW_W)) / (2 * FLOW_W));
    }
    return counts[Math.min(2, Math.floor(x))];
  };
  return xs.map((x) => {
    const v = value(x);
    return {
      x,
      s0: x <= 1 ? v : null,
      s1: x >= 1 && x <= 2 ? v : null,
      s2: x >= 2 ? v : null,
    };
  });
}

function pct(n, of) {
  return of > 0 ? Math.round((n / of) * 100) + "%" : "0%";
}

function FlowPanel({ stats, sub, animate }) {
  const f = stats.flow;
  const steps = [
    { label: "Received", count: f.received, share: f.received > 0 ? "100%" : "0%", note: "STATUS check-ins left out" },
    {
      label: "Acknowledged",
      count: f.acknowledged,
      share: pct(f.acknowledged, f.received),
      note: f.median_ack_s === null ? "No acknowledge times yet" : "Median " + formatDuration(f.median_ack_s) + " after received",
    },
    {
      label: "Resolved",
      count: f.resolved,
      share: pct(f.resolved, f.received),
      note: f.median_resolve_s === null ? "No resolve times yet" : "Median " + formatDuration(f.median_resolve_s) + " after acknowledged",
    },
  ];
  const points = useMemo(() => flowPoints([f.received, f.acknowledged, f.resolved]), [f.received, f.acknowledged, f.resolved]);
  const label = "Response flow, " + sub + ": " + f.received + " received, " + f.acknowledged + " acknowledged, " + f.resolved + " resolved.";
  return (
    <Panel id="ov-flow" title="Response flow" sub={sub} className="ov-span-12">
      <div className="flow">
        <div className="flow-steps">
          {steps.map((s) => (
            <div key={s.label} className="flow-step">
              <p className="flow-label">{s.label}</p>
              <p className="flow-count">
                <span className="flow-number">{s.count}</span>
                <span className="flow-share">{s.share}</span>
              </p>
              <p className="flow-note">{s.note}</p>
            </div>
          ))}
        </div>
        {f.received > 0 && (
          <div role="img" aria-label={label} className="flow-chart">
            <ResponsiveContainer width="100%" height={96}>
              <AreaChart data={points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }} accessibilityLayer={false}>
                <XAxis dataKey="x" type="number" domain={[0, 3]} hide />
                <YAxis hide domain={[0, f.received]} />
                <ChartTooltip
                  cursor={false}
                  isAnimationActive={false}
                  wrapperStyle={{ outline: "none" }}
                  content={({ active, payload }) => {
                    if (!active || !payload || !payload.length) return null;
                    const s = steps[Math.min(2, Math.floor(payload[0].payload.x))];
                    return <TipBox title={s.label} rows={[{ label: "Alerts", value: s.count + " (" + s.share + ")", color: "var(--color-flow-" + (steps.indexOf(s) + 1) + ")" }]} />;
                  }}
                />
                {["s0", "s1", "s2"].map((key, i) => (
                  <Area
                    key={key}
                    type="linear"
                    dataKey={key}
                    stroke="none"
                    fill={"var(--color-flow-" + (i + 1) + ")"}
                    fillOpacity={1}
                    connectNulls={false}
                    activeDot={false}
                    isAnimationActive={animate}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
        <span className="flow-divider" style={{ left: "33.333%" }} aria-hidden="true" />
        <span className="flow-divider" style={{ left: "66.667%" }} aria-hidden="true" />
      </div>
      {f.received === 0 && <PanelEmpty />}
    </Panel>
  );
}

// ---------- Alerts by type ----------

function TypesPanel({ stats, rows, sub, animate }) {
  const [withStatus, setWithStatus] = useState(false);
  const types = TYPE_ORDER.filter((t) => withStatus || t !== "STATUS");
  const totals = Object.fromEntries(types.map((t) => [t, rows.reduce((s, r) => s + r[t], 0)]));
  const any = types.some((t) => totals[t] > 0);
  const unit = stats.per_hour ? "hour" : "day";
  const label =
    "Alerts per " + unit + " by type, " + sub + ": " + types.map((t) => totals[t] + " " + typeMeta(t).label.toLowerCase()).join(", ") + ".";
  return (
    <Panel
      id="ov-types"
      title="Alerts by type"
      sub={sub}
      className="ov-span-7"
      tools={
        <span className="toggle-row">
          <span id="ov-status-toggle" className="toggle-label">
            Include STATUS
          </span>
          <Switch labelledBy="ov-status-toggle" checked={withStatus} onChange={setWithStatus} />
        </span>
      }
    >
      <ul className="legend" aria-label="Legend">
        {types.map((t) => (
          <li key={t} className="legend-item">
            <span className="legend-line" style={{ "--key": LINE_COLOR[t] }} aria-hidden="true" />
            <TypeTag type={t} />
          </li>
        ))}
      </ul>
      {!any ? (
        <PanelEmpty />
      ) : (
        <>
          <div role="img" aria-label={label} className="chart-box">
            <ResponsiveContainer width="100%" height={208}>
              <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} accessibilityLayer={false}>
                <CartesianGrid vertical={false} stroke="var(--color-border)" strokeWidth={1} />
                <XAxis dataKey="tick" {...AXIS} padding={{ left: 12, right: 12 }} interval={tickInterval(stats)} minTickGap={12} />
                <YAxis {...AXIS} width={32} allowDecimals={false} domain={[0, (max) => Math.max(2, max)]} />
                <ChartTooltip
                  cursor={CURSOR}
                  isAnimationActive={false}
                  wrapperStyle={{ outline: "none" }}
                  content={({ active, payload }) =>
                    active && payload && payload.length ? (
                      <TipBox
                        title={payload[0].payload.title}
                        rows={types.map((t) => ({ label: typeMeta(t).label, value: payload[0].payload[t], color: LINE_COLOR[t] }))}
                      />
                    ) : null
                  }
                />
                {types.map((t) => (
                  <Line
                    key={t}
                    type="monotone"
                    dataKey={t}
                    stroke={LINE_COLOR[t]}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--color-panel)", fill: LINE_COLOR[t] }}
                    isAnimationActive={animate}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="visually-hidden"><table>
            <caption>{label}</caption>
            <thead>
              <tr>
                <th scope="col">{unit === "hour" ? "Hour" : "Day"}</th>
                {types.map((t) => (
                  <th key={t} scope="col">
                    {typeMeta(t).label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.title}>
                  <th scope="row">{r.title}</th>
                  {types.map((t) => (
                    <td key={t}>{r[t]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table></div>
        </>
      )}
    </Panel>
  );
}

// ---------- When alerts happen ----------

function heatLevel(n, max) {
  if (n === 0 || max === 0) return 0;
  return Math.min(4, Math.ceil((n / max) * 4));
}

function HeatPanel({ stats, sub, timeFormat }) {
  const grid = stats.weekday_hour;
  const max = Math.max(0, ...grid.flat());
  let busiest = null;
  grid.forEach((row, d) =>
    row.forEach((n, h) => {
      if (n > 0 && (!busiest || n > busiest.n)) busiest = { d, h, n };
    }),
  );
  const label =
    "Alerts by weekday and hour, " +
    sub +
    (busiest ? ". Busiest: " + WEEKDAYS[busiest.d] + " " + hourLong(busiest.h, timeFormat) + ", " + plural(busiest.n, "alert") + "." : ".");
  const tip = (d, h, n) => WEEKDAYS[d] + " " + hourLong(h, timeFormat) + ": " + plural(n, "alert");
  return (
    <Panel id="ov-heat" title="When alerts happen" sub={sub} className="ov-span-5">
      {max === 0 ? (
        <PanelEmpty />
      ) : (
        <>
          <div role="img" aria-label={label} className="heat">
            {grid.map((row, d) => (
              <div key={d} className="heat-row">
                <span className="heat-day">{WEEKDAYS[d]}</span>
                {row.map((n, h) => (
                  <span
                    key={h}
                    className="heat-cell"
                    style={{ background: "var(--color-heat-" + heatLevel(n, max) + ")" }}
                    onMouseEnter={(e) => showTooltip(e.currentTarget, { label: tip(d, h, n) }, 0)}
                    onMouseLeave={(e) => hideTooltip(e.currentTarget)}
                  />
                ))}
              </div>
            ))}
            <div className="heat-row heat-hours" aria-hidden="true">
              <span className="heat-day" />
              {grid[0].map((_, h) => (
                <span key={h} className="heat-hour">
                  {h % 6 === 0 ? hourTick(h, timeFormat) : ""}
                </span>
              ))}
            </div>
          </div>
          <div className="heat-foot">
            <span className="heat-scale" aria-hidden="true">
              Fewer
              {[0, 1, 2, 3, 4].map((l) => (
                <span key={l} className="heat-cell heat-key" style={{ background: "var(--color-heat-" + l + ")" }} />
              ))}
              More
            </span>
            {stats.days < 7 && <span className="heat-note">Based on the selected range</span>}
          </div>
          <div className="visually-hidden"><table>
            <caption>{label}</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                {grid[0].map((_, h) => (
                  <th key={h} scope="col">
                    {hourLong(h, timeFormat)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.map((row, d) => (
                <tr key={d}>
                  <th scope="row">{WEEKDAYS[d]}</th>
                  {row.map((n, h) => (
                    <td key={h}>{n}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table></div>
        </>
      )}
    </Panel>
  );
}

// ---------- loading ----------

function LoadingPanels() {
  return (
    <>
      <section className="panel ov-span-7" aria-hidden="true">
        <Skeleton height={16} width={96} />
        <div className="alerts-body skel-gap">
          <div className="skel-stack">
            <Skeleton height={36} width={72} />
            <Skeleton height={14} width={160} />
          </div>
          <Skeleton height={168} />
        </div>
      </section>
      <section className="panel ov-span-5" aria-hidden="true">
        <Skeleton height={16} width={96} />
        <div className="stats skel-gap">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skel-stack">
              <Skeleton height={32} width={64} />
              <Skeleton height={12} width={80} />
            </div>
          ))}
        </div>
      </section>
      <section className="panel ov-span-12" aria-hidden="true">
        <Skeleton height={16} width={120} />
        <div className="skel-gap">
          <Skeleton height={176} />
        </div>
      </section>
      <section className="panel ov-span-7" aria-hidden="true">
        <Skeleton height={16} width={120} />
        <div className="skel-gap">
          <Skeleton height={240} />
        </div>
      </section>
      <section className="panel ov-span-5" aria-hidden="true">
        <Skeleton height={16} width={140} />
        <div className="skel-gap">
          <Skeleton height={176} />
        </div>
      </section>
    </>
  );
}

// ---------- page ----------

export default function OverviewPage({ timeFormat }) {
  const [range, setRangeState] = useState(loadRange);
  const setRange = (next) => {
    setRangeState(next);
    saveRange(next);
  };
  const error = rangeError(range);
  const key = range.from + "/" + range.to;
  const sub = error ? "" : rangeText(range.from, range.to);

  const [result, setResult] = useState(null); // { key, stats }
  const [failed, setFailed] = useState(false);
  const seq = useRef(0);
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
    [key],
  );

  const reduced = useReducedMotion();
  const animate = !reduced;
  const stats = result && result.key === key ? result.stats : null;
  const rows = useMemo(() => (stats ? seriesRows(stats, timeFormat) : []), [stats, timeFormat]);

  return (
    <div className="page page--overview">
      <header className="page-header">
        <div className="page-head-stack">
          <h1 className="page-title">Overview</h1>
          <p className="page-sub num">{error ? "No range picked" : sub}</p>
        </div>
        <div className="view-tools">
          <RangePicker range={range} setRange={setRange} />
          {/* PDF reports come later. For now Export downloads every alert in the range as CSV. */}
          <button type="button" className="btn btn-secondary" disabled={!!error} onClick={() => downloadCsv(range.from, range.to)}>
            <Download {...ICON} />
            Export CSV
          </button>
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
                <AlertsPanel stats={stats} rows={rows} sub={sub} animate={animate} />
                <SummaryPanel stats={stats} sub={sub} />
                <FlowPanel stats={stats} sub={sub} animate={animate} />
                <TypesPanel stats={stats} rows={rows} sub={sub} animate={animate} />
                <HeatPanel stats={stats} sub={sub} timeFormat={timeFormat} />
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
