import { ago, formatDateTime } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";
import { LinkTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";

export function Battery({ value }) {
  if (value === null || value === undefined) return <span className="muted">No reading</span>;
  const level = value < 10 ? "critical" : value < 20 ? "low" : "ok";
  return (
    <span className="battery">
      <span className="battery-num num">{value}%</span>
      <span className="battery-track" aria-hidden="true">
        <span className={"battery-fill battery-fill--" + level} style={{ width: Math.max(4, value) + "%" }} />
      </span>
      {level === "low" && <span className="battery-word battery-word--low">Low</span>}
      {level === "critical" && <span className="battery-word battery-word--critical">Very low</span>}
    </span>
  );
}

export function deviceName(d) {
  if (d.student_name) return d.student_name;
  return d.role === "REF" ? "Reference board" : "No name";
}

export default function DevicesPage({ devices, loadFailed, nowServer, timeFormat, onOpen, registerFocus }) {
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
          </tr>
        </thead>
        <tbody>
          {devices.map((d) => (
            <tr key={d.device_id} className="device-row" onClick={() => onOpen(d.device_id)}>
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
              <td className="num">
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
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return (
    <div className="page page--devices">
      <header className="page-header">
        <div className="page-head-main">
          <h1 className="page-title">Devices</h1>
          <p className="view-meta num">
            {devices ? devices.length + (devices.length === 1 ? " device" : " devices") : ""}
          </p>
        </div>
      </header>
      <div className="page-body">
        <div className="table-pane table-pane--full">{body}</div>
      </div>
    </div>
  );
}
