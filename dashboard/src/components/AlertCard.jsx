import { forwardRef } from "react";
import { LinkLozenge, StateLozenge, TypeLozenge } from "./Lozenge.jsx";
import { ago, locationLine, studentName } from "../lib/format.js";

/** One alert in the list. The whole card is a button that opens the peek. */
const AlertCard = forwardRef(function AlertCard({ alert, nowServer, onOpen, onHover }, ref) {
  const medicalOpen = alert.alert_type === "MEDICAL" && !alert.acknowledged;
  const className = "card" + (medicalOpen ? " card--medical-open" : "") + (alert.acknowledged ? " card--acknowledged" : "");

  return (
    <button
      ref={ref}
      type="button"
      className={className}
      onClick={() => onOpen(alert.id)}
      onMouseEnter={() => onHover(alert.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(alert.id)}
      onBlur={() => onHover(null)}
      aria-haspopup="dialog"
    >
      <span className="card-row card-row--top">
        <TypeLozenge type={alert.alert_type} />
        <span className="card-age num">{ago(nowServer - alert.timestamp)}</span>
      </span>
      <span className="card-row">
        <span className="card-name">{studentName(alert)}</span>
        <span className="card-id">{alert.device_id}</span>
      </span>
      <span className="card-row card-loc">{locationLine(alert)}</span>
      <span className="card-row card-row--tags">
        <StateLozenge acknowledged={alert.acknowledged} />
        <LinkLozenge link={alert.link} />
      </span>
    </button>
  );
});

export default AlertCard;
