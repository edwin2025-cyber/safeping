import { ago, formatDateTime, formatPa, temperatureText } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";
import { LinkTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";

const LOW = 20; // percent, like Overview
const CRITICAL = 10;
const SEEN_S = 24 * 3600;
const REF_FRESH_S = 120; // same rule as the top bar: a reading in the last 2 minutes

/** "good" (20% and up), "low" (under 20%), "critical" (under 10%), or null with no reading. */
export function batteryLevel(value) {
  if (value === null || value === undefined) return null;
  return value < CRITICAL ? "critical" : value < LOW ? "low" : "good";
}

const BATTERY_WORD = { good: "Good", low: "Low", critical: "Very low" };

/** The level word as heavy colored text: green Good, yellow Low, red Very low. */
export function BatteryTag({ level, children }) {
  return <span className={"battery-word battery-word--" + level}>{children || BATTERY_WORD[level]}</span>;
}

/** The number and a thin 40 px bar: green 20% and up, yellow under 20%, red under 10%.
 *  Low and very low batteries also get their word as a tag, so the color is never the only sign. */
export function Battery({ value }) {
  const level = batteryLevel(value);
  if (!level) return <span className="muted">No reading</span>;
  return (
    <span className={"battery battery--" + level}>
      <span className="battery-num num">{value}%</span>
      <span className="battery-track" aria-hidden="true">
        <span className={"battery-fill battery-fill--" + level} style={{ width: Math.max(4, value) + "%" }} />
      </span>
      {level !== "good" && <BatteryTag level={level} />}
    </span>
  );
}

export function deviceName(d) {
  if (d.student_name) return d.student_name;
  return d.role === "REF" ? "Reference board" : "No name";
}

function plural(n, one, many) {
  return n + " " + (n === 1 ? one : many);
}

/** "4 Fobs, 1 low battery, all seen today". Only the problem part is orange. */
function Summary({ devices, nowServer }) {
  const fobs = devices.filter((d) => d.role !== "REF");
  if (!fobs.length) return <span>No Fobs registered</span>;
  const low = fobs.filter((d) => d.battery !== null && d.battery !== undefined && d.battery < LOW).length;
  const unseen = fobs.filter((d) => !d.last_seen || nowServer - d.last_seen > SEEN_S).length;
  return (
    <span>
      {plural(fobs.length, "Fob", "Fobs")},{" "}
      {low ? <span className="tone-yellow">{plural(low,"low battery", "low batteries")}</span> : "no low batteries"},{" "}
      {unseen ? <span className="tone-orange">{unseen} not seen today</span> : "all seen today"}
    </span>
  );
}

/** When the Fob last started, and "All checks passed" or the failed parts in plain words.
    The full list and the last 10 starts are in the device panel. */
function LastStart({ boot, nowServer, timeFormat }) {
  if (!boot) return <span className="muted">Not reported yet</span>;
  const checks = boot.all_passed ? "All checks passed" : boot.failed.join(", ");
  // The Reference board also reports its pressure sensor ("BME280@0x77").
  const result = boot.sensor ? checks + ". Sensor " + boot.sensor.replace("@", " at ") : checks;
  return (
    <span className="boot-cell">
      <Tooltip label={formatDateTime(boot.time, timeFormat) + (boot.reset_words ? ". " + boot.reset_words : "")}>
        <span className="num cell-muted">
          {ago(nowServer - boot.time)}
          {boot.crashed && <span className="tone-orange">, after a crash</span>}
        </span>
      </Tooltip>
      <Tooltip label={result}>
        <span className={"boot-result" + (boot.all_passed ? "" : " tone-orange")}>
          {boot.all_passed ? result : plural(boot.failed.length, "problem", "problems") + ": " + result}
        </span>
      </Tooltip>
    </span>
  );
}

function OpenButton({ device, onOpen }) {
  return (
    <span className="row-actions">
      <Tooltip label="Open">
        <button
          type="button"
          className="icon-btn icon-btn-sm"
          aria-label={"Open " + deviceName(device)}
          aria-haspopup="dialog"
          onClick={(event) => {
            event.stopPropagation();
            onOpen(device.device_id);
          }}
        >
          <Icon icon={icons.openRow} size={14} />
        </button>
      </Tooltip>
    </span>
  );
}

/** The Reference board: last reading, pressure and temperature. Its own table, under the Fobs. */
function ReferenceTable({ refs, nowServer, timeFormat, onOpen, selectedId, registerFocus }) {
  return (
    <section className="ref-block" aria-labelledby="ref-block-title">
      <h2 id="ref-block-title" className="ref-block-title">
        Reference board
      </h2>
      <table className="table device-table ref-table">
        <colgroup>
          <col className="col-dname" />
          <col className="col-did" />
          <col className="col-seen" />
          <col className="col-pressure" />
          <col className="col-temp" />
          <col className="col-samples" />
          <col className="col-boot" />
          <col className="col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Board</th>
            <th scope="col">ID</th>
            <th scope="col">Last reading</th>
            <th scope="col">Pressure</th>
            <th scope="col">Temperature</th>
            <th scope="col">Readings</th>
            <th scope="col">Last start</th>
            <th scope="col">
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {refs.map((d) => {
            const r = d.reference;
            const age = r ? nowServer - r.time : null;
            const fresh = age !== null && age <= REF_FRESH_S;
            return (
              <tr key={d.device_id} className={"device-row" + (d.device_id === selectedId ? " is-selected" : "")} onClick={() => onOpen(d.device_id)}>
                <td>
                  <button
                    ref={(node) => registerFocus(d.device_id, node)}
                    type="button"
                    className="row-open"
                    aria-haspopup="dialog"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpen(d.device_id);
                    }}
                  >
                    <span className="student-name">{deviceName(d)}</span>
                  </button>
                </td>
                <td className="cell-muted">{d.device_id}</td>
                <td className="num cell-muted">
                  {r ? (
                    <Tooltip label={formatDateTime(r.time, timeFormat) + (fresh ? "" : ". Nothing in the last 2 minutes")}>
                      <span className="ref-seen">
                        <span className={"dot dot--" + (fresh ? "green" : "orange")} aria-hidden="true" />
                        <span className={fresh ? "" : "tone-orange"}>{ago(age)}</span>
                      </span>
                    </Tooltip>
                  ) : (
                    <span className="ref-seen">
                      <span className="dot dot--orange" aria-hidden="true" />
                      <span className="tone-orange">No reading yet</span>
                    </span>
                  )}
                </td>
                <td className="num">{r ? formatPa(r.pressure) : <span className="muted">None</span>}</td>
                <td className="num">{(r && temperatureText(r.temperature)) || <span className="muted">None</span>}</td>
                <td className="num cell-muted">{r && r.samples ? r.samples + " in 30 s" : <span className="muted">Not sent</span>}</td>
                <td>
                  <LastStart boot={d.last_boot} nowServer={nowServer} timeFormat={timeFormat} />
                </td>
                <td className="cell-actions">
                  <OpenButton device={d} onOpen={onOpen} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export default function DevicesPage({ devices, loadFailed, nowServer, timeFormat, onOpen, selectedId, registerFocus }) {
  let body;
  const fobs = devices ? devices.filter((d) => d.role !== "REF") : [];
  const refs = devices ? devices.filter((d) => d.role === "REF") : [];
  if (devices === null) {
    body = <p className="loading">{loadFailed ? "Waiting for the server." : "Loading devices."}</p>;
  } else if (!devices.length) {
    body = (
      <div className="empty">
        <Icon icon={icons.devices} size={24} />
        <p className="empty-title">No devices yet</p>
        <p className="empty-text">Register a Fob with add_device.py in the server folder.</p>
      </div>
    );
  } else {
    body = (
      <>
      {fobs.length > 0 && (
      <table className="table device-table">
        <colgroup>
          <col className="col-dname" />
          <col className="col-did" />
          <col className="col-seen" />
          <col className="col-battery" />
          <col className="col-boot" />
          <col className="col-link" />
          <col className="col-open" />
          <col className="col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Student</th>
            <th scope="col">Fob ID</th>
            <th scope="col">Last seen</th>
            <th scope="col">Battery</th>
            <th scope="col">Last start</th>
            <th scope="col">Link</th>
            <th scope="col" className="right">
              Open alerts
            </th>
            <th scope="col">
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {fobs.map((d) => (
            <tr key={d.device_id} className={"device-row" + (d.device_id === selectedId ? " is-selected" : "")} onClick={() => onOpen(d.device_id)}>
              <td>
                <button
                  ref={(node) => registerFocus(d.device_id, node)}
                  type="button"
                  className="row-open"
                  aria-haspopup="dialog"
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpen(d.device_id);
                  }}
                >
                  <span className={"student-name" + (d.student_name ? "" : " is-muted")}>{deviceName(d)}</span>
                </button>
              </td>
              <td className="cell-muted">{d.device_id}</td>
              <td className="num cell-muted">
                {d.last_seen ? (
                  <Tooltip label={formatDateTime(d.last_seen, timeFormat)}>
                    <span>{ago(nowServer - d.last_seen)}</span>
                  </Tooltip>
                ) : (
                  <span className="muted">Never</span>
                )}
              </td>
              <td>
                <Battery value={d.battery} />
              </td>
              <td>
                <LastStart boot={d.last_boot} nowServer={nowServer} timeFormat={timeFormat} />
              </td>
              <td>
                <LinkTag link={d.link} />
              </td>
              <td className={"num right" + (d.open_alerts ? " strong" : " cell-muted")}>{d.open_alerts}</td>
              <td className="cell-actions">
                <OpenButton device={d} onOpen={onOpen} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
      {refs.length > 0 && (
        <ReferenceTable refs={refs} nowServer={nowServer} timeFormat={timeFormat} onOpen={onOpen} selectedId={selectedId} registerFocus={registerFocus} />
      )}
      </>
    );
  }

  return (
    <div className="page page--devices">
      <header className="page-header">
        <div className="page-head-stack">
          <h1 className="page-title">Devices</h1>
          <p className="page-sub num">{devices && devices.length > 0 ? <Summary devices={devices} nowServer={nowServer} /> : " "}</p>
        </div>
      </header>
      <div className="page-body">
        <div className="table-pane table-pane--full">{body}</div>
      </div>
    </div>
  );
}
