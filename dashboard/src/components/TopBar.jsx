import { useEffect, useState } from "react";
import { Clock, Gauge, RadioTower, ServerOff } from "lucide-react";
import { Pill } from "./Lozenge.jsx";
import { ago, formatClock } from "../lib/format.js";

const RELAY_RECENT_S = 15 * 60;

function relayPill(status) {
  const title =
    "Time since the last alert that came in over LoRa (USB serial bridge). The Relay sends no heartbeat, so a quiet Relay is not a fault.";
  const age = status ? status.last_lora_age_s : null;
  if (age === null || age === undefined) {
    return { color: "gray", text: "Relay: no data", title };
  }
  return { color: age <= RELAY_RECENT_S ? "green" : "gray", text: "Relay: last alert " + ago(age), title };
}

function referencePill(status, maxAge) {
  const age = status ? status.reference_age_s : null;
  if (age === null || age === undefined) {
    return { color: "gray", text: "Reference: no reading", title: "No pressure reading from the Reference board yet." };
  }
  if (age <= 60) return { color: "green", text: "Reference: " + ago(age), title: "Floors can be worked out." };
  if (age <= maxAge) {
    return { color: "orange", text: "Reference: " + ago(age), title: "Reading is getting old." };
  }
  return {
    color: "red",
    text: "Reference: stale, " + ago(age),
    title: "Older than " + maxAge + " s, so indoor floors cannot be worked out.",
  };
}

function ServerClock({ skew, timeFormat }) {
  const [now, setNow] = useState(() => Date.now() / 1000 + skew);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000 + skew), 1000);
    setNow(Date.now() / 1000 + skew);
    return () => clearInterval(timer);
  }, [skew]);
  return (
    <Pill color="gray" Icon={Clock} title="Server time" label={"Server time " + formatClock(now, timeFormat)}>
      {formatClock(now, timeFormat)}
    </Pill>
  );
}

export default function TopBar({ title, status, unreachable, skew, timeFormat, refMaxAge }) {
  const relay = relayPill(status);
  const ref = referencePill(status, refMaxAge);
  return (
    <header className="topbar">
      <h1 className="page-title">{title}</h1>
      <div className="pills">
        <span role="status" className="pill-live">
          {unreachable && (
            <Pill color="orange" Icon={ServerOff} title="The last update failed. Retrying automatically.">
              Server not reachable
            </Pill>
          )}
        </span>
        <Pill color={relay.color} Icon={RadioTower} title={relay.title}>
          {relay.text}
        </Pill>
        <Pill color={ref.color} Icon={Gauge} title={ref.title}>
          {ref.text}
        </Pill>
        <ServerClock skew={skew} timeFormat={timeFormat} />
      </div>
    </header>
  );
}
