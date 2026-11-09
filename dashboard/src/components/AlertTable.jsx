import { alertState, isOpenMedical } from "../lib/alertMeta.js";
import { ago, formatDateTime, placeText, studentName } from "../lib/format.js";
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

function AlertRow({ alert, compact, nowServer, timeFormat, highlighted, onOpen, onHover, registerFocus }) {
  const cls = ["alert-row"];
  if (isOpenMedical(alert)) cls.push("is-medical-open");
  if (highlighted) cls.push("is-hovered");
  return (
    <tr
      className={cls.join(" ")}
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
          <span className="student-id">{alert.device_id}</span>
        </button>
        {compact && (
          <span className="cell-sub">
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
        <Tooltip label={formatDateTime(alert.timestamp, timeFormat)}>
          <span>{ago(nowServer - alert.timestamp)}</span>
        </Tooltip>
      </td>
      <td>
        <StatusDot alert={alert} />
      </td>
    </tr>
  );
}

/** Alerts as table rows. In the All view, rows are grouped by state with quiet labels. */
export default function AlertTable({ alerts, grouped, compact, nowServer, timeFormat, highlightedId, onOpen, onHover, registerFocus }) {
  const groups = grouped
    ? GROUPS.map((g) => ({ ...g, items: alerts.filter((a) => alertState(a) === g.state) })).filter((g) => g.items.length)
    : [{ state: "all", items: alerts }];
  const columns = compact ? 4 : 5;
  return (
    <table className={"table alert-table" + (compact ? " is-compact" : "")}>
      <colgroup>
        <col className="col-type" />
        <col className="col-student" />
        {!compact && <col className="col-place" />}
        <col className="col-time" />
        <col className="col-status" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col">Type</th>
          <th scope="col">Student</th>
          {!compact && <th scope="col">Place</th>}
          <th scope="col">Time</th>
          <th scope="col">Status</th>
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
              nowServer={nowServer}
              timeFormat={timeFormat}
              highlighted={a.id === highlightedId}
              onOpen={onOpen}
              onHover={onHover}
              registerFocus={registerFocus}
            />
          ))}
        </tbody>
      ))}
    </table>
  );
}
