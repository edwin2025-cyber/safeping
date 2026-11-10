import { useState } from "react";
import { alertState, isUrgentOpen, typeMeta } from "../lib/alertMeta.js";
import { ago, formatDateTime, placeText, studentName } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";
import { StatusDot, TypeTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";

const GROUPS = [
  { state: "open", label: "Needs action" },
  { state: "acknowledged", label: "Acknowledged" },
  { state: "resolved", label: "Resolved" },
];

function Place({ alert }) {
  const text = placeText(alert);
  return text ? <span>{text}</span> : <span className="muted">Unknown</span>;
}

/** Ghost icon buttons in their own narrow column at the right end of a row. They show on
    hover or keyboard focus, and never cover the time or the status. */
function RowActions({ alert, onOpen, onAck }) {
  const [busy, setBusy] = useState(false);
  const name = studentName(alert);
  const open = alertState(alert) === "open";
  async function ack(event) {
    event.stopPropagation();
    if (busy) return;
    setBusy(true);
    try {
      await onAck(alert.id);
    } catch {
      // The row stays Open. The Peek shows errors; here the next poll tells the truth.
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="row-actions">
      {open && onAck && (
        <Tooltip label="Acknowledge">
          <button type="button" className="icon-btn icon-btn-sm" aria-label={"Acknowledge " + name + "'s alert"} aria-disabled={busy || undefined} onClick={ack}>
            <Icon icon={icons.acknowledged} />
          </button>
        </Tooltip>
      )}
      <Tooltip label="Open">
        <button
          type="button"
          className="icon-btn icon-btn-sm"
          aria-label={"Open " + name + "'s alert"}
          aria-haspopup="dialog"
          onClick={(event) => {
            event.stopPropagation();
            onOpen(alert.id);
          }}
        >
          <Icon icon={icons.openRow} size={14} />
        </button>
      </Tooltip>
    </span>
  );
}

function AlertRow({ alert, compact, showStatus, nowServer, timeFormat, selected, onOpen, onAck, onHover, registerFocus }) {
  const urgent = isUrgentOpen(alert);
  return (
    <tr
      className={"alert-row" + (selected ? " is-selected" : "")}
      onClick={() => onOpen(alert.id)}
      onMouseEnter={() => onHover(alert.id)}
      onMouseLeave={() => onHover(null)}
    >
      <td>
        <TypeTag type={alert.alert_type} />
      </td>
      <td className="cell-student">
        <button
          ref={(node) => registerFocus(alert.id, node)}
          type="button"
          className="row-open"
          onClick={(event) => {
            event.stopPropagation();
            onOpen(alert.id);
          }}
          onFocus={() => onHover(alert.id)}
          onBlur={() => onHover(null)}
          aria-haspopup="dialog"
        >
          <span className="student-name">{studentName(alert)}</span>
          {!compact && <span className="student-id">{alert.device_id}</span>}
        </button>
        {compact && (
          <span className="cell-sub">
            <span className="student-id">{alert.device_id}</span>
            <span className="cell-sub-sep" aria-hidden="true">
              ·
            </span>
            <Place alert={alert} />
          </span>
        )}
      </td>
      {!compact && (
        <td className="cell-place">
          <Place alert={alert} />
        </td>
      )}
      <td className="cell-time num">
        <span className="time-wrap">
          <span
            className={"dot" + (urgent ? " dot--pulse dot--" + typeMeta(alert.alert_type).key : " dot--none")}
            aria-hidden="true"
          />
          {urgent && <span className="visually-hidden">Urgent, </span>}
          <Tooltip label={formatDateTime(alert.timestamp, timeFormat)}>
            <span>{ago(nowServer - alert.timestamp)}</span>
          </Tooltip>
        </span>
      </td>
      {showStatus && (
        <td>
          <StatusDot alert={alert} />
        </td>
      )}
      <td className="cell-actions">
        <RowActions alert={alert} onOpen={onOpen} onAck={onAck} />
      </td>
    </tr>
  );
}

/** Alerts as calm table rows. In the All view, rows are grouped by state with quiet labels.
    Under Needs action every row is Open, so the Status column is left out there. Split view
    leaves it out too, so names have room: its rows are already filtered or grouped by state. */
export default function AlertTable({
  alerts,
  grouped,
  showStatus = true,
  compact,
  nowServer,
  timeFormat,
  selectedId,
  onOpen,
  onAck,
  onHover,
  registerFocus,
}) {
  const groups = grouped
    ? GROUPS.map((g) => ({ ...g, items: alerts.filter((a) => alertState(a) === g.state) })).filter((g) => g.items.length)
    : [{ state: "all", items: alerts }];
  const columns = (compact ? 4 : 5) + (showStatus ? 1 : 0);
  return (
    <table className={"table alert-table" + (compact ? " is-compact" : "")}>
      <colgroup>
        <col className="col-type" />
        <col className="col-student" />
        {!compact && <col className="col-place" />}
        <col className="col-time" />
        {showStatus && <col className="col-status" />}
        <col className="col-actions" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col">Type</th>
          <th scope="col">Student</th>
          {!compact && <th scope="col">Place</th>}
          <th scope="col">Time</th>
          {showStatus && <th scope="col">Status</th>}
          <th scope="col">
            <span className="visually-hidden">Actions</span>
          </th>
        </tr>
      </thead>
      {groups.map((g) => (
        <tbody key={g.state}>
          {grouped && (
            <tr className="group-row">
              <th scope="colgroup" colSpan={columns}>
                <span>{g.label}</span>
                <span className="group-count num">{g.items.length}</span>
              </th>
            </tr>
          )}
          {g.items.map((a) => (
            <AlertRow
              key={a.id}
              alert={a}
              compact={compact}
              showStatus={showStatus}
              nowServer={nowServer}
              timeFormat={timeFormat}
              selected={a.id === selectedId}
              onOpen={onOpen}
              onAck={onAck}
              onHover={onHover}
              registerFocus={registerFocus}
            />
          ))}
        </tbody>
      ))}
    </table>
  );
}
