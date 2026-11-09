import "./DevicesPage.css";
import { Cpu } from "lucide-react";
import { ago, formatDateTime } from "../lib/format.js";
import { LinkLozenge } from "./Lozenge.jsx";

function Battery({ value }) {
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

export default function DevicesPage({ devices, loadFailed, nowServer, timeFormat }) {
  if (devices === null) {
    return (
      <div className="page-pad">
        <p className="muted">{loadFailed ? "Waiting for the server." : "Loading devices."}</p>
      </div>
    );
  }
  if (!devices.length) {
    return (
      <div className="page-pad">
        <div className="empty">
          <Cpu size={24} aria-hidden="true" />
          <p>No devices registered. Add one with add_device.py in the server folder.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-pad">
      <div className="table-wrap">
        <table className="devices">
          <caption className="visually-hidden">Registered devices</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Device ID</th>
              <th scope="col">Role</th>
              <th scope="col">Last seen</th>
              <th scope="col">Battery</th>
              <th scope="col" className="right">
                Last counter
              </th>
              <th scope="col">Link</th>
              <th scope="col" className="right">
                Open alerts
              </th>
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => (
              <tr key={d.device_id}>
                <td className="strong">{d.student_name || (d.role === "REF" ? "Reference sensor" : "Not set")}</td>
                <td>{d.device_id}</td>
                <td>{d.role === "REF" ? "Reference" : "Fob"}</td>
                <td className="num">
                  {d.last_seen ? (
                    <span title={formatDateTime(d.last_seen, timeFormat)}>{ago(nowServer - d.last_seen)}</span>
                  ) : (
                    <span className="muted">Never</span>
                  )}
                </td>
                <td>
                  <Battery value={d.battery} />
                </td>
                <td className="num right">{d.last_counter ?? <span className="muted">None</span>}</td>
                <td>
                  <LinkLozenge link={d.link} />
                </td>
                <td className={"num right" + (d.open_alerts ? " strong" : "")}>{d.open_alerts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
