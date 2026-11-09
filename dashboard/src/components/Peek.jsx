import "./Peek.css";
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { Building2, Check, MapPin, Video, X } from "lucide-react";
import { MapContainer } from "react-leaflet";
import { hasGps, zoneRadius } from "../lib/alertMeta.js";
import { useReducedMotion } from "../lib/theme.js";
import {
  ago,
  areaLine,
  cameraText,
  coords,
  detailsText,
  formatDateTime,
  locationLine,
  studentName,
  temperatureText,
} from "../lib/format.js";
import CopyButton from "./CopyButton.jsx";
import { LinkLozenge, StateLozenge, TypeLozenge } from "./Lozenge.jsx";
import { AlertMarker, AlertZones, AttributionPrefix, BaseTiles } from "./mapParts.jsx";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function PeekMap({ alert, settings, theme, cartoKey }) {
  const reducedMotion = useReducedMotion();
  const radius = Math.max(zoneRadius(alert, settings.sightRadius), 20);
  const bounds = L.latLng(alert.latitude, alert.longitude).toBounds(radius * 2.4);
  return (
    <MapContainer
      key={alert.id}
      bounds={bounds}
      boundsOptions={{ maxZoom: 18 }}
      zoomSnap={0.5}
      className="peek-map"
      scrollWheelZoom={false}
      zoomAnimation={!reducedMotion}
      fadeAnimation={!reducedMotion}
    >
      <BaseTiles theme={theme} labels={settings.mapLabels} cartoKey={cartoKey} />
      <AttributionPrefix />
      <AlertZones alert={alert} sightRadius={settings.sightRadius} />
      <AlertMarker alert={alert} />
    </MapContainer>
  );
}

function CameraBox({ alert, settings }) {
  const cam = cameraText(alert, settings);
  return (
    <section className="camera-box" aria-labelledby="camera-title">
      <div className="camera-head">
        <h3 id="camera-title">
          <Video size={16} aria-hidden="true" />
          Review cameras
        </h3>
        <CopyButton getText={() => cam.text} />
      </div>
      <dl className="camera-grid">
        <dt>Window</dt>
        <dd className="num">
          {formatDateTime(cam.start, settings.timeFormat, false)} to {formatDateTime(cam.end, settings.timeFormat, false)}
          <span className="hint">
            {" "}
            ({settings.cameraBefore} min before, {settings.cameraAfter} min after)
          </span>
        </dd>
        <dt>Area</dt>
        <dd className="num">{cam.area}</dd>
      </dl>
    </section>
  );
}

function Row({ label, children }) {
  return (
    <>
      <dt>{label}</dt>
      <dd className="num">{children}</dd>
    </>
  );
}

export default function Peek({ alert, settings, theme, cartoKey, nowServer, onClose, onAck, onResolve }) {
  const dialogRef = useRef(null);
  const [busy, setBusy] = useState(null); // "ack" or "resolve"
  const [error, setError] = useState(null);

  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Focus the dialog once, on open. Esc closes from anywhere, even inside the map.
  useEffect(() => {
    dialogRef.current && dialogRef.current.focus();
    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function trapFocus(event) {
    if (event.key !== "Tab") return;
    const items = Array.from(dialogRef.current.querySelectorAll(FOCUSABLE)).filter((el) => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function run(kind, action) {
    setBusy(kind);
    setError(null);
    try {
      await action(alert.id);
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setBusy(null);
    }
  }

  const gps = hasGps(alert);
  const area = areaLine(alert, settings.sightRadius);
  const temp = temperatureText(alert.temperature);

  return (
    <div
      className="peek-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="peek"
        role="dialog"
        aria-modal="true"
        aria-labelledby="peek-title"
        tabIndex={-1}
        onKeyDown={trapFocus}
      >
        <header className="peek-head">
          <div className="peek-tags">
            <TypeLozenge type={alert.alert_type} />
            <StateLozenge acknowledged={alert.acknowledged} />
            <LinkLozenge link={alert.link} />
          </div>
          <div className="peek-title-row">
            <h2 id="peek-title">{studentName(alert)}</h2>
            <span className="peek-id">{alert.device_id}</span>
          </div>
          <p className="peek-time num">
            {formatDateTime(alert.timestamp, settings.timeFormat)}
            <span className="peek-ago"> ({ago(nowServer - alert.timestamp)})</span>
          </p>
          <button type="button" className="icon-btn peek-close" onClick={onClose} aria-label="Close">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <div className="peek-body">
          {gps ? (
            <div className="peek-map-wrap">
              <PeekMap alert={alert} settings={settings} theme={theme} cartoKey={cartoKey} />
            </div>
          ) : (
            <div className="peek-nomap">
              <Building2 size={20} aria-hidden="true" />
              <span>No GPS fix. {locationLine(alert)}.</span>
            </div>
          )}
          {area && (
            <p className="peek-area num">
              <MapPin size={14} aria-hidden="true" />
              {area}
            </p>
          )}

          <dl className="details">
            <Row label="Received">{formatDateTime(alert.timestamp, settings.timeFormat)}</Row>
            <Row label="Fob time">
              {alert.device_ts ? formatDateTime(alert.device_ts, settings.timeFormat) : "Not sent"}
            </Row>
            <Row label="Location">
              {gps ? coords(alert) + (alert.accuracy !== null ? ", within " + alert.accuracy + " m" : "") : locationLine(alert)}
            </Row>
            <Row label="Floor">{alert.floor !== null ? alert.floor : gps ? "Not needed (GPS)" : "Not worked out"}</Row>
            <Row label="Pressure">{alert.pressure !== null ? alert.pressure + " Pa" : "Not sent"}</Row>
            <Row label="Temperature">{temp || "Not recorded"}</Row>
            <Row label="Battery">{alert.battery !== null ? alert.battery + "%" : "Not sent"}</Row>
            <Row label="Counter">{alert.counter !== null && alert.counter !== undefined ? alert.counter : "Not recorded"}</Row>
            <Row label="Link">
              <LinkLozenge link={alert.link} />
            </Row>
            {alert.alert_type !== "STATUS" && <Row label="Text to duty phone">{alert.sms_sent ? "Sent" : "Not sent"}</Row>}
            {alert.acknowledged && alert.acknowledged_at && (
              <Row label="Acknowledged">{formatDateTime(alert.acknowledged_at, settings.timeFormat)}</Row>
            )}
          </dl>

          {alert.alert_type === "SUSPICIOUS" && <CameraBox alert={alert} settings={settings} />}
        </div>

        <footer className="peek-foot">
          {error && (
            <p className="peek-error" role="alert">
              {error}
            </p>
          )}
          <div className="peek-actions">
            {!alert.acknowledged && (
              <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => run("ack", onAck)}>
                <Check size={16} aria-hidden="true" />
                {busy === "ack" ? "Acknowledging" : "Acknowledge"}
              </button>
            )}
            <button type="button" className="btn" disabled={busy !== null} onClick={() => run("resolve", onResolve)}>
              {busy === "resolve" ? "Resolving" : "Resolve"}
            </button>
            <CopyButton getText={() => detailsText(alert, settings)} label="Copy details" />
          </div>
        </footer>
      </div>
    </div>
  );
}
