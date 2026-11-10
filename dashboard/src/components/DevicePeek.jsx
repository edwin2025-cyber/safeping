import { useState } from "react";
import { TYPE_ORDER, typeMeta } from "../lib/alertMeta.js";
import { ago, formatDateTime, placeText } from "../lib/format.js";
import { batteryIcon, icons } from "../lib/icons.js";
import { Select } from "./Controls.jsx";
import { Battery, deviceName } from "./DevicesPage.jsx";
import Icon from "./Icon.jsx";
import Modal from "./Modal.jsx";
import { LinkTag, StatusDot, TypeTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";

function Prop({ icon, label, children }) {
  return (
    <div className="prop">
      <dt>
        <Icon icon={icon} fixed />
        {label}
      </dt>
      <dd className="num">{children}</dd>
    </div>
  );
}

export default function DevicePeek({ device, history, historyFailed, nowServer, timeFormat, onClose, returnFocus }) {
  const [typeFilter, setTypeFilter] = useState("ALL");
  const rows = history ? history.filter((a) => typeFilter === "ALL" || a.alert_type === typeFilter) : null;
  const isRef = device.role === "REF";

  return (
    <Modal onClose={onClose} labelledBy="device-title" className="peek" returnFocus={returnFocus}>
      <div className="peek-strip">
        <nav className="crumbs" aria-label="Breadcrumb">
          <span>Devices</span>
          <span className="crumb-sep" aria-hidden="true">
            /
          </span>
          <span className="crumb-current">{deviceName(device)}</span>
        </nav>
        <div className="peek-strip-actions">
          <Tooltip label="Close" shortcut="Esc">
            <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
              <Icon icon={icons.close} />
            </button>
          </Tooltip>
        </div>
      </div>

      <div className="peek-scroll">
        <article className="peek-page">
          <div className="peek-title-row">
            <h2 id="device-title">{deviceName(device)}</h2>
            <span className="peek-id">{device.device_id}</span>
          </div>

          <dl className="props">
            <Prop icon={icons.devices} label={isRef ? "Board" : "Fob ID"}>
              {device.device_id}
              {isRef && <span className="muted"> (ground floor pressure)</span>}
            </Prop>
            <Prop icon={icons.time} label="Last seen">
              {device.last_seen ? (
                <>
                  {formatDateTime(device.last_seen, timeFormat)} <span className="muted">({ago(nowServer - device.last_seen)})</span>
                </>
              ) : (
                <span className="muted">Never</span>
              )}
            </Prop>
            {!isRef && (
              <Prop icon={batteryIcon(device.battery)} label="Battery">
                <Battery value={device.battery} />
              </Prop>
            )}
            {device.link && device.link !== "unknown" && (
              <Prop icon={device.link === "wifi" ? icons.wifi : icons.lora} label="Link">
                <LinkTag link={device.link} />
              </Prop>
            )}
            <Prop icon={icons.messageNumber} label="Message number">
              {device.last_counter !== null ? device.last_counter : <span className="muted">None yet</span>}
            </Prop>
            {!isRef && (
              <Prop icon={icons.open} label="Open alerts">
                {device.open_alerts}
              </Prop>
            )}
          </dl>

          {!isRef && (
            <section className="history" aria-labelledby="history-title">
              <div className="history-head">
                <h3 id="history-title">
                  <Icon icon={icons.history} />
                  Alert history
                  {history && <span className="history-count num">{history.length}</span>}
                </h3>
                <Select
                  label="Filter history by type"
                  value={typeFilter}
                  onChange={setTypeFilter}
                  options={[{ value: "ALL", label: "All types" }, ...TYPE_ORDER.map((t) => ({ value: t, label: typeMeta(t).label }))]}
                />
              </div>
              {rows === null ? (
                <p className="loading">{historyFailed ? "Waiting for the server." : "Loading history."}</p>
              ) : rows.length === 0 ? (
                <div className="empty">
                  <Icon icon={icons.inbox} size={24} />
                  <p className="empty-title">{typeFilter === "ALL" ? "No alerts from this Fob yet" : "No alerts of this type"}</p>
                </div>
              ) : (
                <table className="table history-table">
                  <colgroup>
                    <col className="col-type" />
                    <col className="col-pressed" />
                    <col className="col-place" />
                    <col className="col-status" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th scope="col">Type</th>
                      <th scope="col">Pressed</th>
                      <th scope="col">Place</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((a) => (
                      <tr key={a.id}>
                        <td>
                          <TypeTag type={a.alert_type} />
                        </td>
                        <td className="num">
                          {formatDateTime(a.timestamp, timeFormat, false)} <span className="muted">({ago(nowServer - a.timestamp)})</span>
                        </td>
                        <td>{placeText(a) || <span className="muted">Unknown</span>}</td>
                        <td>
                          <StatusDot alert={a} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}
        </article>
      </div>
    </Modal>
  );
}
