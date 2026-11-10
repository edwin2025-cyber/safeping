import { Fragment, useEffect, useState } from "react";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";
import Tooltip from "./Tooltip.jsx";
import { Tag } from "./Tags.jsx";
import { MOCK } from "../lib/api.js";
import { agoShort, formatNumber, formatTime } from "../lib/format.js";

const RELAY_RECENT_S = 15 * 60;
const CLOCK_MS = 15000;

// Hidden "widest" text under each value, so a value never changes the width of the bar.
// Numbers are tabular, so 0 is as wide as any other digit.
const RELAY_WIDEST = ["00 min ago", "no data"];
const REF_WIDEST = ["000,000 Pa", "no reading"];
const CLOCK_WIDEST = { 12: ["00:00 PM", "00:00 AM"], 24: ["00:00"] };

function relayItem(status) {
  const tip = "Time since the last alert that came in over LoRa. The Relay sends no heartbeat, so a quiet Relay is not a fault.";
  const age = status ? status.last_lora_age_s : null;
  if (age === null || age === undefined) return { color: "gray", value: "no data", tip };
  return { color: age <= RELAY_RECENT_S ? "green" : "gray", value: agoShort(age), tip };
}

function referenceItem(status, maxAge) {
  const age = status ? status.reference_age_s : null;
  if (age === null || age === undefined) {
    return { color: "gray", value: "no reading", tip: "No pressure reading from the ground floor board yet." };
  }
  const value = formatNumber(status.reference_pressure) + " Pa";
  const when = "Ground floor pressure, read " + agoShort(age) + ".";
  if (age <= 60) return { color: "green", value, tip: when + " Indoor floors can be worked out." };
  if (age <= maxAge) return { color: "orange", value, tip: when + " The reading is getting old." };
  return { color: "red", value, tip: when + " Older than " + maxAge + " s, so indoor floors cannot be worked out." };
}

/** The value on top of its hidden widest texts. */
function Fixed({ value, widest }) {
  return (
    <span className="si-value">
      <span>{value}</span>
      {widest.map((w) => (
        <span key={w} className="si-ghost" aria-hidden="true">
          {w}
        </span>
      ))}
    </span>
  );
}

function StatusItem({ color, label, value, widest, tip, className = "" }) {
  return (
    <Tooltip label={tip}>
      <span className={"status-item " + className} tabIndex={0} aria-label={label + ": " + value + ". " + tip}>
        {color && <span className={"dot dot--" + color} aria-hidden="true" />}
        <span className="si-label">{label}</span>
        <Fixed value={value} widest={widest} />
      </span>
    </Tooltip>
  );
}

/** Server time, no seconds. Updates every 15 seconds. */
function ServerClock({ skew, timeFormat }) {
  const [now, setNow] = useState(() => Date.now() / 1000 + skew);
  useEffect(() => {
    setNow(Date.now() / 1000 + skew);
    const timer = setInterval(() => setNow(Date.now() / 1000 + skew), CLOCK_MS);
    return () => clearInterval(timer);
  }, [skew]);
  const text = formatTime(now, timeFormat);
  return (
    <Tooltip label="Server time">
      <span className="status-item si-clock" tabIndex={0} aria-label={"Server time " + text}>
        <Fixed value={text} widest={CLOCK_WIDEST[timeFormat === "24" ? 24 : 12]} />
      </span>
    </Tooltip>
  );
}

/** Shown the whole time the empty preview is on, so nobody mistakes it for the real dashboard. */
export function PreviewBanner({ onExit }) {
  return (
    <div className="preview-banner" role="status">
      <Icon icon={icons.warning} size={14} />
      <span className="preview-banner-text">
        <strong>Empty dashboard preview.</strong> This tab shows SafePing on its first day, with no Fobs, alerts or readings. Real alerts are hidden
        here.
      </span>
      <button type="button" className="btn btn-secondary preview-exit" onClick={onExit}>
        Exit preview
      </button>
    </div>
  );
}

export default function TopBar({ crumb, status, unreachable, skew, timeFormat, refMaxAge }) {
  const relay = relayItem(status);
  const ref = referenceItem(status, refMaxAge);
  const items = [];
  if (unreachable) {
    items.push(
      <StatusItem
        key="server"
        className="si-alert"
        color="orange"
        label="Server"
        value="not reachable"
        widest={["not reachable"]}
        tip="The last update failed. The dashboard keeps retrying on its own."
      />,
    );
  }
  items.push(<StatusItem key="relay" color={relay.color} label="Relay" value={relay.value} widest={RELAY_WIDEST} tip={relay.tip} />);
  items.push(<StatusItem key="ref" color={ref.color} label="Reference" value={ref.value} widest={REF_WIDEST} tip={ref.tip} />);
  items.push(<ServerClock key="clock" skew={skew} timeFormat={timeFormat} />);

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
        {MOCK && <Tag color="gray">Mock data</Tag>}
      </nav>
      <span className="visually-hidden" role="status">
        {unreachable ? "Server not reachable" : ""}
      </span>
      <div className="status-group">
        {items.map((item, i) => (
          <Fragment key={item.key}>
            {i > 0 && <span className="status-sep" aria-hidden="true" />}
            {item}
          </Fragment>
        ))}
      </div>
    </header>
  );
}
