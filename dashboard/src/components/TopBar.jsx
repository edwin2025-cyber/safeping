import { useEffect, useState } from "react";
import Tooltip from "./Tooltip.jsx";
import { Tag } from "./Tags.jsx";
import { MOCK } from "../lib/api.js";
import { ago, formatClock, formatNumber } from "../lib/format.js";

const RELAY_RECENT_S = 15 * 60;

function relayItem(status) {
  const tip = "Time since the last alert that came in over LoRa. The Relay sends no heartbeat, so a quiet Relay is not a fault.";
  const age = status ? status.last_lora_age_s : null;
  if (age === null || age === undefined) return { color: "gray", value: "no data", tip };
  return { color: age <= RELAY_RECENT_S ? "green" : "gray", value: "last alert " + ago(age), tip };
}

function referenceItem(status, maxAge) {
  const age = status ? status.reference_age_s : null;
  if (age === null || age === undefined) {
    return { color: "gray", value: "no reading", tip: "No pressure reading from the ground floor board yet." };
  }
  const value = formatNumber(status.reference_pressure) + " Pa";
  const when = "Ground floor pressure, read " + ago(age) + ".";
  if (age <= 60) return { color: "green", value, tip: when + " Indoor floors can be worked out." };
  if (age <= maxAge) return { color: "orange", value, tip: when + " The reading is getting old." };
  return { color: "red", value, tip: when + " Older than " + maxAge + " s, so indoor floors cannot be worked out." };
}

function StatusItem({ color, label, value, tip }) {
  return (
    <Tooltip label={tip}>
      <span className="status-item" tabIndex={0} aria-label={label + ": " + value + ". " + tip}>
        <span className={"dot dot--" + color} aria-hidden="true" />
        <span className="si-label">{label}</span>
        <span className="si-value num">{value}</span>
      </span>
    </Tooltip>
  );
}

function ServerClock({ skew, timeFormat }) {
  const [now, setNow] = useState(() => Date.now() / 1000 + skew);
  useEffect(() => {
    setNow(Date.now() / 1000 + skew);
    const timer = setInterval(() => setNow(Date.now() / 1000 + skew), 1000);
    return () => clearInterval(timer);
  }, [skew]);
  const text = formatClock(now, timeFormat);
  return (
    <Tooltip label="Server time">
      <span className="status-item si-clock num" tabIndex={0} aria-label={"Server time " + text}>
        {text}
      </span>
    </Tooltip>
  );
}

export default function TopBar({ crumb, status, unreachable, skew, timeFormat, refMaxAge }) {
  const relay = relayItem(status);
  const ref = referenceItem(status, refMaxAge);
  return (
    <header className="topbar">
      <nav className="crumbs" aria-label="Breadcrumb">
        <span>SafePing</span>
        <span className="crumb-sep" aria-hidden="true">
          /
        </span>
        <span className="crumb-current" aria-current="page">
          {crumb}
        </span>
        {MOCK && <Tag color="orange">Mock data</Tag>}
      </nav>
      <div className="status-items">
        <span role="status" className="si-live">
          {unreachable && (
            <StatusItem
              color="orange"
              label="Server"
              value="not reachable"
              tip="The last update failed. The dashboard keeps retrying on its own."
            />
          )}
        </span>
        <StatusItem color={relay.color} label="Relay" value={relay.value} tip={relay.tip} />
        <StatusItem color={ref.color} label="Reference" value={ref.value} tip={ref.tip} />
        <ServerClock skew={skew} timeFormat={timeFormat} />
      </div>
    </header>
  );
}
