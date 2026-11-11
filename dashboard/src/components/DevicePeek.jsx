import { useState } from "react";
import { TYPE_ORDER, typeMeta } from "../lib/alertMeta.js";
import { ago, formatDate, formatDateTime, formatTime, placeText } from "../lib/format.js";
import { batteryIcon, icons } from "../lib/icons.js";
import { Select } from "./Controls.jsx";
import { Battery, BatteryTag, batteryLevel, deviceName } from "./DevicesPage.jsx";
import Icon from "./Icon.jsx";
import Modal from "./Modal.jsx";
import { LateTag, LinkTag, StatusDot, Tag, TypeTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";

// How the device panel lays out its facts.
//   "sections": a header, Last seen, Battery and Open alerts cards, then the alert history.
//   "list":     the single list of properties used before, then the alert history.
// To go back to the old panel, set this to "list".
const DEVICE_LAYOUT = "sections";

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

/** The alert history table and its type filter. The same in both layouts. */
function History({ history, historyFailed, nowServer, timeFormat }) {
  const [typeFilter, setTypeFilter] = useState("ALL");
  const rows = history ? history.filter((a) => typeFilter === "ALL" || a.alert_type === typeFilter) : null;
  return (
    <section className="history" aria-labelledby="history-title">
      <div className="history-head">
        <h3 id="history-title">
          <Icon icon={icons.history} />
          Alert history
          {history && <span className="history-count num">{history.length}</span>}
        </h3>
        <Select
          label="Filter history by type"
          align="end"
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
                  <span className="history-when">
                    <span>{formatDateTime(a.timestamp, timeFormat, false)}</span>
                    <span className="muted">{ago(nowServer - a.timestamp)}</span>
                    <LateTag alert={a} timeFormat={timeFormat} />
                  </span>
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
  );
}

/** "All checks passed" or the failed parts in plain words, from one boot report. */
export function BootResult({ boot }) {
  if (boot.all_passed) return <span>All checks passed</span>;
  return <span className="tone-orange">{boot.failed.join(", ")}</span>;
}

/** Why the Fob started (machine.reset_cause() in the BOOT report): "Power on",
    "Restarted after a crash" (orange), and so on. Older firmware did not send it. */
function ResetWords({ boot }) {
  if (!boot.reset_words) return <span className="muted">Not reported</span>;
  return <span className={boot.crashed ? "tone-orange" : undefined}>{boot.reset_words}</span>;
}

/** WiFi at start is information only: no WiFi is not a failure, LoRa still works. */
function bootWifi(boot) {
  if (boot.wifi === null || boot.wifi === undefined) return "WiFi not reported";
  return boot.wifi ? "WiFi joined" : "No WiFi at start (LoRa still works)";
}

/** The Fob's last start and its self-check, then the last 10 starts. From the BOOT
    report the Fob sends at power on (see docs/message-format.md, Boot report). */
function Starts({ device, boots, bootsFailed, nowServer, timeFormat }) {
  const last = device.last_boot;
  return (
    <section className="history starts" aria-labelledby="starts-title">
      <div className="history-head">
        <h3 id="starts-title">
          <Icon icon={icons.boot} />
          Starts and self-checks
          {boots && boots.length > 0 && <span className="history-count num">{boots.length}</span>}
        </h3>
      </div>
      {!last ? (
        <p className="loading">No start reported yet. Fobs with the new firmware report each power on.</p>
      ) : (
        <dl className="kv starts-last">
          <div className="kv-row">
            <dt>Last start</dt>
            <dd className="num">
              {formatDateTime(last.time, timeFormat)} <span className="muted">({ago(nowServer - last.time)})</span>
            </dd>
          </div>
          <div className="kv-row">
            <dt>Why it started</dt>
            <dd>
              <ResetWords boot={last} />
            </dd>
          </div>
          <div className="kv-row">
            <dt>Self-check</dt>
            <dd>
              <BootResult boot={last} />
            </dd>
          </div>
          <div className="kv-row">
            <dt>WiFi</dt>
            <dd className="muted">{bootWifi(last)}</dd>
          </div>
          <div className="kv-row">
            <dt>Firmware</dt>
            <dd className="num">{last.firmware || <span className="muted">Not reported</span>}</dd>
          </div>
        </dl>
      )}
      {boots === null || boots === undefined ? (
        last && <p className="loading">{bootsFailed ? "Waiting for the server." : "Loading starts."}</p>
      ) : (
        boots.length > 1 && (
          <table className="table history-table starts-table">
            <thead>
              <tr>
                <th scope="col">Started</th>
                <th scope="col">Why</th>
                <th scope="col">Self-check</th>
                <th scope="col">WiFi</th>
              </tr>
            </thead>
            <tbody>
              {boots.map((b) => (
                <tr key={b.counter + "-" + b.time}>
                  <td className="num">{formatDateTime(b.time, timeFormat, false)}</td>
                  <td>
                    <ResetWords boot={b} />
                  </td>
                  <td>
                    <BootResult boot={b} />
                  </td>
                  <td>
                    {b.wifi ? (
                      <Tag color="wifi" icon={icons.wifi}>
                        Joined
                      </Tag>
                    ) : (
                      <span className="muted">No</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </section>
  );
}

// ---------- "sections" layout ----------

// The word under the battery bar, as a tag in the bar's color.
const BATTERY_CARD_WORD = { good: "Good", low: "Low, under 20%", critical: "Very low, under 10%" };

function SectionsBody({ device, nowServer, timeFormat, history, historyFailed, boots, bootsFailed }) {
  const isRef = device.role === "REF";
  const level = batteryLevel(device.battery);
  return (
    <article className="peek-page peek-page--sections">
      <header className="peek-head">
        <div className="peek-head-main">
          <h2 id="device-title">{deviceName(device)}</h2>
          <div className="peek-meta">
            <span className="peek-role">
              <Icon icon={icons.devices} size={14} fixed />
              {isRef ? "Reference board" : "Fob"}
            </span>
            {device.link && device.link !== "unknown" && <LinkTag link={device.link} />}
            <span className="peek-id">{device.device_id}</span>
          </div>
        </div>
      </header>

      <div className={"peek-facts peek-facts--three" + (isRef ? " is-ref" : "")}>
        <section className="fact" aria-label="Last seen">
          <div className="fact-label">
            <Icon icon={icons.time} size={12} fixed />
            Last seen
          </div>
          {device.last_seen ? (
            <>
              <div className="fact-main num">{formatTime(device.last_seen, timeFormat)}</div>
              <div className="fact-sub num">
                <span>{formatDate(device.last_seen)}</span>
                <span className="muted">{ago(nowServer - device.last_seen)}</span>
              </div>
            </>
          ) : (
            <div className="fact-main muted">Never</div>
          )}
          <div className="fact-foot num">
            Message number {device.last_counter !== null && device.last_counter !== undefined ? device.last_counter : "none yet"}
          </div>
        </section>

        {isRef ? (
          <section className="fact" aria-label="Role">
            <div className="fact-label">
              <Icon icon={icons.pressure} size={12} fixed />
              Role
            </div>
            <div className="fact-main">Ground floor pressure</div>
            <div className="fact-sub">Indoor floors are worked out against this board.</div>
          </section>
        ) : (
          <section className="fact" aria-label="Battery">
            <div className="fact-label">
              <Icon icon={batteryIcon(device.battery)} size={12} fixed />
              Battery
            </div>
            {level ? (
              <>
                <div className="fact-main num">{device.battery}%</div>
                <span className="fact-bar" aria-hidden="true">
                  <span className={"battery-fill battery-fill--" + level} style={{ width: Math.max(3, device.battery) + "%" }} />
                </span>
                <div className="fact-sub">
                  <BatteryTag level={level}>{BATTERY_CARD_WORD[level]}</BatteryTag>
                </div>
              </>
            ) : (
              <div className="fact-main muted">No reading</div>
            )}
          </section>
        )}

        {!isRef && (
          <section className="fact" aria-label="Open alerts">
            <div className="fact-label">
              <Icon icon={icons.open} size={12} fixed />
              Open alerts
            </div>
            <div className="fact-main num">{device.open_alerts}</div>
            <div className="fact-sub">
              {device.open_alerts > 0 ? (
                <span className="status">
                  <span className="dot dot--open" aria-hidden="true" />
                  Needs action
                </span>
              ) : (
                <span className="muted">None open</span>
              )}
            </div>
          </section>
        )}
      </div>

      {!isRef && <Starts device={device} boots={boots} bootsFailed={bootsFailed} nowServer={nowServer} timeFormat={timeFormat} />}
      {!isRef && <History history={history} historyFailed={historyFailed} nowServer={nowServer} timeFormat={timeFormat} />}
    </article>
  );
}

// ---------- "list" layout (the panel before the sections) ----------

function ListBody({ device, nowServer, timeFormat, history, historyFailed, boots, bootsFailed }) {
  const isRef = device.role === "REF";
  return (
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
      {!isRef && <Starts device={device} boots={boots} bootsFailed={bootsFailed} nowServer={nowServer} timeFormat={timeFormat} />}
      {!isRef && <History history={history} historyFailed={historyFailed} nowServer={nowServer} timeFormat={timeFormat} />}
    </article>
  );
}

export default function DevicePeek({ device, crumb = "Devices", history, historyFailed, boots, bootsFailed, nowServer, timeFormat, onClose, returnFocus }) {
  const Body = DEVICE_LAYOUT === "list" ? ListBody : SectionsBody;
  return (
    <Modal onClose={onClose} labelledBy="device-title" className="peek" returnFocus={returnFocus}>
      <div className="peek-strip">
        <nav className="crumbs" aria-label="Breadcrumb">
          <span>{crumb}</span>
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
        <Body
          device={device}
          nowServer={nowServer}
          timeFormat={timeFormat}
          history={history}
          historyFailed={historyFailed}
          boots={boots}
          bootsFailed={bootsFailed}
        />
      </div>
    </Modal>
  );
}
