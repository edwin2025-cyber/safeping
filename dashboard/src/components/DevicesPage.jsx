import { ago, formatDateTime } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";
import { LinkTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";

const LOW = 20; // percent, like Overview
const CRITICAL = 10;
const SEEN_S = 24 * 3600;

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

export default function DevicesPage({ devices, loadFailed, nowServer, timeFormat, onOpen, selectedId, registerFocus }) {
  let body;
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
      <table className="table device-table">
        <colgroup>
          <col className="col-dname" />
          <col className="col-did" />
          <col className="col-seen" />
          <col className="col-battery" />
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
          {devices.map((d) => (
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
                <LinkTag link={d.link} />
              </td>
              <td className={"num right" + (d.open_alerts ? " strong" : " cell-muted")}>{d.open_alerts}</td>
              <td className="cell-actions">
                <span className="row-actions">
                  <Tooltip label="Open">
                    <button
                      type="button"
                      className="icon-btn icon-btn-sm"
                      aria-label={"Open " + deviceName(d)}
                      aria-haspopup="dialog"
                      onClick={(event) => {
                        event.stopPropagation();
                        onOpen(d.device_id);
                      }}
                    >
                      <Icon icon={icons.openRow} size={14} />
                    </button>
                  </Tooltip>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
