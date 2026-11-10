import { useMemo, useRef, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from "recharts";
import { downloadCsv, getJson } from "../lib/api.js";
import { typeMeta } from "../lib/alertMeta.js";
import { dayCount, dayLong, dayTick, hourLong, hourTick, isoDay, parseDay, presetRange, RANGE_PRESETS, rangeText } from "../lib/dates.js";
import { ago, formatDuration } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import { useReducedMotion } from "../lib/theme.js";
import { usePolling } from "../lib/usePolling.js";
import { Select } from "./Controls.jsx";
import Icon from "./Icon.jsx";
import { Tag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";

const STATS_MS = 30000;
const RANGE_KEY = "safeping.overviewRange";
const TIP_TYPES = ["MEDICAL", "SUSPICIOUS", "SILENT"]; // STATUS is never in the counts
const AXIS = { tickLine: false, axisLine: false, tickMargin: 8, tick: { fontSize: 12, fill: "var(--color-text-subtlest)" } };
const CURSOR = { stroke: "var(--color-border-bold)", strokeWidth: 1 };
const REASONS = {
  bad_signature: "bad signature",
  replay: "replay",
  unknown_device: "unknown device",
  wrong_role: "wrong role",
  bad_format: "bad format",
  bad_json: "bad JSON",
};
const PLACE_ICON = { place: icons.place, gps: icons.gps, floor: icons.floor, none: icons.unknownType };

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

function plural(n, word) {
  return n + " " + word + (n === 1 ? "" : "s");
}

function periodWord(days) {
  return days === 1 ? "the day before" : "previous " + days + " days";
}

function capital(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function Panel({ id, icon, title, tools, className = "", children }) {
  return (
    <section className={"panel " + className} aria-labelledby={id + "-title"}>
      <div className="panel-head">
        <h2 id={id + "-title"} className="panel-title">
          {icon && <Icon icon={icon} className="panel-icon" />}
          {title}
        </h2>
        {tools}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}

function PanelEmpty({ text = "No alerts in this range." }) {
  return (
    <div className="panel-empty">
      <Icon icon={icons.chart} />
      <span>{text}</span>
    </div>
  );
}

function Skeleton({ height, width = "100%" }) {
  return <span className="skel" style={{ height, width }} aria-hidden="true" />;
}

/** Per-day rows (or per-hour rows for a single day) for the trend chart and the sparkline. */
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

// ---------- stat tiles ----------

/** Tiny line of this period's counts, no axes. Decoration: the number next to it says the total. */
function Sparkline({ values }) {
  if (values.length < 2 || !values.some((v) => v > 0)) return null;
  const w = 64;
  const h = 24;
  const pad = 2;
  const max = Math.max(1, ...values);
  const points = values
    .map((v, i) => {
      const x = pad + (i * (w - 2 * pad)) / (values.length - 1);
      const y = h - pad - (v / max) * (h - 2 * pad);
      return x.toFixed(1) + "," + y.toFixed(1);
    })
    .join(" ");
  return (
    <svg className="spark" width={w} height={h} viewBox={"0 0 " + w + " " + h} aria-hidden="true" focusable="false">
      <polyline points={points} fill="none" stroke="var(--color-blue-bold)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/** One stat tile: icon and label, big number, a context line. A link when it goes somewhere. */
function Tile({ icon, label, fullLabel, value, valueTone, muted, context, tone, href, extra }) {
  const body = (
    <>
      <span className="tile-top" title={fullLabel}>
        <Icon icon={icon} fixed />
        <span className="tile-label">{label}</span>
      </span>
      <span className="tile-mid">
        <span className={"tile-value num" + (valueTone ? " tone-" + valueTone : "") + (muted ? " is-muted" : "")}>{value}</span>
        {extra}
      </span>
      <span className={"tile-context" + (tone ? " tone-" + tone : "")} title={context}>
        {context}
      </span>
    </>
  );
  if (!href) return <div className="tile">{body}</div>;
  const where = href === "#/live" ? "Live" : "Devices";
  return (
    <Tooltip label={"Go to " + where}>
      <a className="tile tile--link" href={href} aria-label={label + ": " + value + ". " + context + ". Go to " + where}>
        {body}
      </a>
    </Tooltip>
  );
}

function changeLine(total, previous, days) {
  if (previous === 0) return { tone: "flat", text: "No alerts in " + periodWord(days) };
  if (total === previous) return { tone: "flat", text: "Same as " + periodWord(days) };
  const pct = Math.round((Math.abs(total - previous) / previous) * 100);
  // More alerts is worse, so up is red and down is green.
  return total > previous
    ? { tone: "up", text: "Up " + pct + "% vs " + periodWord(days) }
    : { tone: "down", text: "Down " + pct + "% vs " + periodWord(days) };
}

function fastestType(byType) {
  const entries = Object.entries(byType || {}).filter(([, s]) => s !== null && s !== undefined);
  if (!entries.length) return null;
  entries.sort((a, b) => a[1] - b[1]);
  return { type: entries[0][0], seconds: entries[0][1] };
}

function StatTiles({ stats, rows }) {
  const change = changeLine(stats.total, stats.previous_total, stats.days);
  const median = stats.flow.median_ack_s;
  const fastest = fastestType(stats.median_ack_by_type);
  const stale = stats.stale_fobs || [];
  const low = stats.low_battery_fobs || [];
  const changeTone = { up: "red", down: "green", flat: null }[change.tone];

  let fobsContext = { text: "All seen today", tone: "green" };
  if (stats.fobs_total === 0) fobsContext = { text: "No Fobs registered", tone: null };
  else if (stale.length) fobsContext = { text: stale.length + " not seen in 24 h", tone: "orange" };

  let lowContext = "All above 20%";
  if (low.length === 1) lowContext = low[0].name + ", " + low[0].pct + "%";
  else if (low.length > 1) lowContext = low.length + " students";

  return (
    <div className="tiles" role="group" aria-label="Summary">
      <Tile
        icon={icons.alerts}
        label="Alerts"
        value={stats.total}
        context={change.text}
        tone={changeTone}
        extra={<Sparkline values={rows.map((r) => r.current)} />}
      />
      <Tile
        icon={icons.medianAck}
        label="Time to acknowledge"
        fullLabel="Median time to acknowledge"
        value={median === null ? "No data" : formatDuration(median)}
        muted={median === null}
        extra={median === null ? null : <span className="tile-unit">median</span>}
        context={fastest ? typeMeta(fastest.type).label + " fastest, " + formatDuration(fastest.seconds) : "No acknowledge times yet"}
      />
      <Tile
        icon={icons.openNow}
        label="Open now"
        value={stats.open_now}
        context={stats.open_medical_now > 0 ? stats.open_medical_now + " Medical" : "None urgent"}
        tone={stats.open_medical_now > 0 ? "red" : null}
        href="#/live"
      />
      <Tile
        icon={icons.fobsActive}
        label="Fobs active"
        value={stats.fobs_active + " of " + stats.fobs_total}
        context={fobsContext.text}
        tone={fobsContext.tone}
        href="#/devices"
      />
      <Tile
        icon={icons.lowBattery}
        label="Low battery"
        value={stats.low_battery}
        valueTone={stats.low_battery > 0 ? "orange" : null}
        context={lowContext}
        href="#/devices"
      />
    </div>
  );
}

// ---------- Alerts over time ----------

function TrendTip({ row }) {
  return (
    <div className="chart-tip">
      <div className="chart-tip-title">{row.title}</div>
      <div className="chart-tip-row">
        <span className="chart-tip-key" style={{ "--key": "var(--color-blue-bold)" }} aria-hidden="true" />
        <span className="chart-tip-label">This period</span>
        <span className="chart-tip-value num">{row.current}</span>
      </div>
      <div className="chart-tip-types">
        {TIP_TYPES.map((t) => (
          <span key={t} className="chart-tip-type">
            <Icon icon={typeMeta(t).icon} size={12} fixed />
            {typeMeta(t).label} <span className="num">{row[t] || 0}</span>
          </span>
        ))}
      </div>
      <div className="chart-tip-row">
        <span className="chart-tip-key is-dashed" style={{ "--key": "var(--color-gray-bold)" }} aria-hidden="true" />
        <span className="chart-tip-label">{row.prevTitle}</span>
        <span className="chart-tip-value num">{row.previous}</span>
      </div>
    </div>
  );
}

function TrendPanel({ stats, rows, sub, animate }) {
  const empty = stats.total === 0 && stats.previous_total === 0;
  const unit = stats.per_hour ? "hour" : "day";
  const label = "Alerts per " + unit + ", " + sub + ", " + stats.total + " total. Previous period: " + stats.previous_total + ".";
  const legend = (
    <ul className="mini-legend" aria-hidden="true">
      <li>
        <span className="legend-line" style={{ "--key": "var(--color-blue-bold)" }} />
        This period
      </li>
      <li>
        <span className="legend-line is-dashed" style={{ "--key": "var(--color-gray-bold)" }} />
        {capital(periodWord(stats.days))}
      </li>
    </ul>
  );
  return (
    <Panel id="ov-trend" icon={icons.overview} title="Alerts over time" tools={!empty && legend} className="ov-trend">
      {empty ? (
        <PanelEmpty />
      ) : (
        <>
          <div role="img" aria-label={label} className="chart-fill">
            <div className="chart-abs">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} accessibilityLayer={false}>
                  <CartesianGrid vertical={false} stroke="var(--color-border)" strokeWidth={1} />
                  <XAxis dataKey="tick" {...AXIS} padding={{ left: 8, right: 8 }} interval={tickInterval(stats)} minTickGap={12} />
                  <YAxis {...AXIS} width={28} allowDecimals={false} tickCount={3} domain={[0, (max) => Math.max(2, Math.ceil(max / 2) * 2)]} />
                  <ChartTooltip
                    cursor={CURSOR}
                    isAnimationActive={false}
                    wrapperStyle={{ outline: "none" }}
                    content={({ active, payload }) => (active && payload && payload.length ? <TrendTip row={payload[0].payload} /> : null)}
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
          </div>
          <div className="visually-hidden">
            <table>
              <caption>{label}</caption>
              <thead>
                <tr>
                  <th scope="col">{unit === "hour" ? "Hour" : "Day"}</th>
                  <th scope="col">Alerts</th>
                  {TIP_TYPES.map((t) => (
                    <th key={t} scope="col">
                      {typeMeta(t).label}
                    </th>
                  ))}
                  <th scope="col">Previous period</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.title}>
                    <th scope="row">{r.title}</th>
                    <td>{r.current}</td>
                    {TIP_TYPES.map((t) => (
                      <td key={t}>{r[t] || 0}</td>
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

// ---------- Response flow ----------

function share(n, of) {
  return of > 0 ? Math.round((n / of) * 100) + "%" : "0%";
}

function FlowPanel({ stats }) {
  const f = stats.flow;
  const steps = [
    { label: "Received", count: f.received, note: null },
    {
      label: "Acknowledged",
      count: f.acknowledged,
      note: f.median_ack_s === null ? "No acknowledge times yet" : "Median " + formatDuration(f.median_ack_s) + " after received",
    },
    {
      label: "Resolved",
      count: f.resolved,
      note: f.median_resolve_s === null ? "No resolve times yet" : "Median " + formatDuration(f.median_resolve_s) + " after acknowledged",
    },
  ];
  return (
    <Panel id="ov-flow" icon={icons.medianAck} title="Response flow" className="ov-flow">
      <ol className="flow-list">
        {steps.map((s, i) => (
          <li key={s.label} className="flow-row">
            <div className="flow-line">
              <span className="flow-label">{s.label}</span>
              <span className="flow-count num">{s.count}</span>
              <span className="flow-share num">{share(s.count, f.received)}</span>
            </div>
            <span className="bar-slot" aria-hidden="true">
              <span
                className="bar"
                style={{ width: (f.received > 0 ? (s.count / f.received) * 100 : 0) + "%", background: "var(--color-flow-" + (i + 1) + ")" }}
              />
            </span>
            {s.note && <p className="flow-note">{s.note}</p>}
          </li>
        ))}
      </ol>
      <p className="panel-note panel-foot">STATUS check-ins not counted</p>
    </Panel>
  );
}

// ---------- Hotspots ----------

function HotspotsPanel({ stats }) {
  const h = stats.hotspots || { places: [], more_count: 0 };
  const located = h.places.filter((p) => p.kind !== "none");
  const max = Math.max(1, ...h.places.map((p) => p.count));
  return (
    <Panel id="ov-hot" icon={icons.hotspots} title="Hotspots" className="ov-half">
      {located.length === 0 ? (
        <PanelEmpty text="No alerts with a location in this range." />
      ) : (
        <ol className="hot-list">
          {h.places.map((p) => (
            <li key={p.label} className="hot-row">
              <span className="hot-label">
                <Icon icon={PLACE_ICON[p.kind] || icons.place} size={14} fixed />
                <span className="hot-name" title={p.label}>
                  {p.label}
                </span>
              </span>
              <span className="bar-slot" aria-hidden="true">
                <span className="bar" style={{ width: (p.count / max) * 100 + "%", background: "var(--color-blue-bold)" }} />
              </span>
              <span className="hot-count num">{p.count}</span>
            </li>
          ))}
          {h.more_count > 0 && <li className="hot-more">and {plural(h.more_count, "more place")}</li>}
        </ol>
      )}
    </Panel>
  );
}

// ---------- System health ----------

function HealthRow({ icon, label, children, sub, tone }) {
  return (
    <div className="health-row">
      <dt>
        <Icon icon={icon} size={14} fixed />
        {label}
      </dt>
      <dd className={tone ? "tone-" + tone : undefined}>
        <span className="health-value">{children}</span>
        {sub && <span className="health-sub">{sub}</span>}
      </dd>
    </div>
  );
}

function HealthPanel({ stats, refMaxAge }) {
  const d = stats.delivery || { lora: 0, wifi: 0, unknown: 0 };
  const rej = stats.rejected;
  const stale = stats.stale_fobs || [];
  const low = stats.low_battery_fobs || [];
  const reasons = rej ? Object.entries(rej.by_reason).sort((a, b) => b[1] - a[1]) : [];
  const attack = rej && ((rej.by_reason.bad_signature || 0) > 0 || (rej.by_reason.replay || 0) > 0);
  const age = stats.reference_age_s;
  const deliveryEmpty = d.lora + d.wifi + d.unknown === 0;

  return (
    <Panel id="ov-health" icon={icons.health} title="System health" className="ov-half">
      <dl className="health">
        <HealthRow icon={icons.live} label="Delivery">
          {deliveryEmpty ? (
            <span className="muted">No messages in this range</span>
          ) : (
            <span className="health-tags">
              <Tag color="gray" icon={icons.lora}>
                LoRa <span className="num">{d.lora}</span>
              </Tag>
              <Tag color="teal" icon={icons.wifi}>
                WiFi <span className="num">{d.wifi}</span>
              </Tag>
              {d.unknown > 0 && (
                <Tag color="gray" icon={icons.unknownType}>
                  Unknown <span className="num">{d.unknown}</span>
                </Tag>
              )}
            </span>
          )}
        </HealthRow>
        <HealthRow icon={icons.duplicates} label="Duplicates caught">
          {stats.duplicates === null || stats.duplicates === undefined ? (
            <Tooltip label="The server cannot tell a resend from a replay yet. Both count under Rejected messages as replay.">
              <span className="muted" tabIndex={0}>
                Not tracked
              </span>
            </Tooltip>
          ) : (
            <span className="num">{stats.duplicates}</span>
          )}
        </HealthRow>
        <HealthRow
          icon={icons.rejected}
          label="Rejected messages"
          tone={attack ? "red" : null}
          sub={reasons.length ? reasons.map(([r, n]) => n + " " + (REASONS[r] || r.replaceAll("_", " "))).join(", ") : null}
        >
          {rej === null || rej === undefined ? (
            <span className="muted">Not tracked</span>
          ) : (
            <>
              {attack && <Icon icon={icons.warning} size={14} />}
              <span className="num">{rej.total}</span>
            </>
          )}
        </HealthRow>
        <HealthRow icon={icons.time} label="Fobs not seen in 24 h" tone={stale.length ? "orange" : null}>
          {stale.length > 0 && <span className="health-names">{stale.join(", ")}</span>}
          <span className="num">{stale.length}</span>
        </HealthRow>
        <HealthRow icon={icons.lowBattery} label="Low battery" tone={low.length ? "orange" : null}>
          {low.length > 0 && <span className="health-names">{low.map((f) => f.name + " " + f.pct + "%").join(", ")}</span>}
          <span className="num">{low.length}</span>
        </HealthRow>
        <HealthRow icon={icons.pressure} label="Reference sensor" tone={age === null || age === undefined || age > refMaxAge ? "orange" : null}>
          {age === null || age === undefined ? "No reading" : "Last reading " + ago(age)}
        </HealthRow>
      </dl>
    </Panel>
  );
}

// ---------- loading ----------

function LoadingPanels() {
  return (
    <>
      <div className="tiles" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="tile">
            <Skeleton height={14} width={96} />
            <Skeleton height={28} width={56} />
            <Skeleton height={12} width={120} />
          </div>
        ))}
      </div>
      {["ov-trend", "ov-flow", "ov-half", "ov-half"].map((c, i) => (
        <section key={i} className={"panel " + c} aria-hidden="true">
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

export default function OverviewPage({ timeFormat, refMaxAge = 120 }) {
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
      <header className="page-header ov-header">
        <div className="ov-head-text">
          <h1 className="page-title">Overview</h1>
          <p className="page-sub num">{error ? "No range picked" : sub}</p>
        </div>
        <div className="view-tools">
          <RangePicker range={range} setRange={setRange} />
          {/* PDF reports come later. For now Export downloads every alert in the range as CSV. */}
          <button type="button" className="btn btn-secondary" disabled={!!error} onClick={() => downloadCsv(range.from, range.to)}>
            <Icon icon={icons.download} />
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
                <StatTiles stats={stats} rows={rows} />
                <TrendPanel stats={stats} rows={rows} sub={sub} animate={animate} />
                <FlowPanel stats={stats} />
                <HotspotsPanel stats={stats} />
                <HealthPanel stats={stats} refMaxAge={refMaxAge} />
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
