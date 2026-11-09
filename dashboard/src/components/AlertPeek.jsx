import { useState } from "react";
import L from "../lib/leafletSetup.js";
import {
  BatteryMedium,
  Building2,
  Check,
  CircleCheckBig,
  Clock,
  Crosshair,
  ExternalLink,
  Gauge,
  Hash,
  Layers,
  MapPin,
  Maximize2,
  MessageSquare,
  RadioTower,
  Thermometer,
  Video,
  X,
} from "lucide-react";
import { MapContainer } from "react-leaflet";
import { alertState, hasGps, linkMeta, zoneRadius } from "../lib/alertMeta.js";
import {
  ago,
  areaLine,
  cameraInfo,
  coords,
  detailsText,
  formatDate,
  formatDateTime,
  formatNumber,
  formatTime,
  googleMapsUrl,
  placeText,
  studentName,
  temperatureText,
} from "../lib/format.js";
import { useReducedMotion } from "../lib/theme.js";
import CopyButton from "./CopyButton.jsx";
import Modal from "./Modal.jsx";
import { LinkTag, StatusDot, TypeTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";
import { AlertZones, AttributionPrefix, BaseTiles, LocateFixed, MAX_ZOOM, MapControls, SizeWatcher, StaticMarker } from "./mapParts.jsx";

const ICON = { size: 16, strokeWidth: 1.75, "aria-hidden": true };

function Prop({ Icon, label, children }) {
  return (
    <div className="prop">
      <dt>
        <Icon {...ICON} />
        {label}
      </dt>
      <dd className="num">{children}</dd>
    </div>
  );
}

function boundsFor(alert, sightRadius) {
  const radius = Math.max(zoneRadius(alert, sightRadius), 20);
  return L.latLng(alert.latitude, alert.longitude).toBounds(radius * 2.6);
}

function PeekMap({ alert, settings, update, theme, cartoKey }) {
  const [map, setMap] = useState(null);
  const reducedMotion = useReducedMotion();
  return (
    <div className="map-wrap peek-map">
      <MapContainer
        ref={setMap}
        key={alert.id}
        bounds={boundsFor(alert, settings.sightRadius)}
        boundsOptions={{ maxZoom: 18 }}
        maxZoom={MAX_ZOOM}
        zoomSnap={0.5}
        zoomControl={false}
        scrollWheelZoom={false}
        className="map"
        zoomAnimation={!reducedMotion}
        fadeAnimation={!reducedMotion}
      >
        <BaseTiles theme={theme} labels={settings.mapLabels} cartoKey={cartoKey} />
        <AttributionPrefix />
        <SizeWatcher />
        <AlertZones alert={alert} sightRadius={settings.sightRadius} />
        <StaticMarker alert={alert} />
      </MapContainer>
      <MapControls
        map={map}
        onFit={() => map && map.fitBounds(boundsFor(alert, settings.sightRadius), { maxZoom: 18, animate: !reducedMotion })}
        fitLabel="Center on the alert"
        FitIcon={LocateFixed}
        labels={settings.mapLabels}
        onToggleLabels={() => update({ mapLabels: !settings.mapLabels })}
        hasKey={!!cartoKey}
        reducedMotion={reducedMotion}
      />
    </div>
  );
}

function CameraCallout({ alert, settings }) {
  const cam = cameraInfo(alert, settings);
  const sameDay = formatDate(cam.start) === formatDate(cam.end);
  return (
    <section className="callout callout--yellow" aria-labelledby="camera-title">
      <div className="callout-head">
        <Video {...ICON} className="callout-icon" />
        <h3 id="camera-title">Review cameras</h3>
      </div>
      <p className="callout-window num">
        {formatTime(cam.start, settings.timeFormat)} to {formatTime(cam.end, settings.timeFormat)}
      </p>
      <p className="callout-text num">
        {sameDay ? formatDate(cam.start) : formatDate(cam.start) + " to " + formatDate(cam.end)}, {settings.cameraBefore} min before and{" "}
        {settings.cameraAfter} min after the press
      </p>
      <p className="callout-text num">
        {cam.place ? cam.place + ", " : ""}
        {cam.area}
      </p>
      <div className="callout-actions">
        <CopyButton getText={() => cam.text} label="Copy for security" />
      </div>
    </section>
  );
}

export default function AlertPeek({ alert, settings, update, theme, cartoKey, nowServer, onClose, onAck, onResolve, returnFocus }) {
  const [busy, setBusy] = useState(null); // "ack" or "resolve"
  const [error, setError] = useState(null);
  const state = alertState(alert);
  const gps = hasGps(alert);
  const place = placeText(alert);
  const link = linkMeta(alert.link);
  const area = areaLine(alert, settings.sightRadius);

  async function run(kind, action) {
    setBusy(kind);
    setError(null);
    try {
      await action(alert.id);
    } catch {
      setError("The server did not answer. Try again in a moment.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal onClose={onClose} labelledBy="peek-title" className="peek" returnFocus={returnFocus}>
      <div className="peek-strip">
        <nav className="crumbs" aria-label="Breadcrumb">
          <span>Live</span>
          <span className="crumb-sep" aria-hidden="true">
            /
          </span>
          <span className="crumb-current">{studentName(alert)}</span>
        </nav>
        <div className="peek-strip-actions">
          <CopyButton getText={() => detailsText(alert, settings)} label="Copy details" variant="ghost" />
          <Tooltip label="Open full page" shortcut="Coming soon">
            <button type="button" className="icon-btn" aria-label="Open full page (coming soon)" aria-disabled="true">
              <Maximize2 {...ICON} />
            </button>
          </Tooltip>
          <Tooltip label="Close" shortcut="Esc">
            <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
              <X {...ICON} />
            </button>
          </Tooltip>
        </div>
      </div>

      <div className="peek-scroll">
        <article className="peek-page">
          <div className="peek-title-row">
            <h2 id="peek-title">{studentName(alert)}</h2>
            <span className="peek-id">{alert.device_id}</span>
            <TypeTag type={alert.alert_type} />
            <StatusDot state={state} />
          </div>

          {state !== "resolved" && (
            <div className="peek-actions">
              {state === "open" && (
                <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => run("ack", onAck)}>
                  <Check {...ICON} />
                  {busy === "ack" ? "Acknowledging" : "Acknowledge"}
                </button>
              )}
              <button type="button" className="btn btn-secondary" disabled={busy !== null} onClick={() => run("resolve", onResolve)}>
                <CircleCheckBig {...ICON} />
                {busy === "resolve" ? "Resolving" : "Resolve"}
              </button>
              {error && (
                <p className="peek-error" role="alert">
                  {error}
                </p>
              )}
            </div>
          )}

          <dl className="props">
            <Prop Icon={Clock} label="Pressed">
              {formatDateTime(alert.timestamp, settings.timeFormat)} <span className="muted">({ago(nowServer - alert.timestamp)})</span>
            </Prop>
            <Prop Icon={MapPin} label="Place">
              {place || <span className="muted">Unknown</span>}
            </Prop>
            <Prop Icon={Building2} label="Floor">
              {alert.floor !== null ? alert.floor : <span className="muted">{gps ? "Not needed, GPS fix" : "Not worked out"}</span>}
            </Prop>
            <Prop Icon={Crosshair} label="GPS">
              {gps ? (
                <span className="prop-gps">
                  <span>
                    {coords(alert)}
                    {alert.accuracy !== null ? ", within " + alert.accuracy + " m" : ""}
                  </span>
                  <a href={googleMapsUrl(alert)} target="_blank" rel="noopener noreferrer">
                    Open in Google Maps
                    <ExternalLink size={12} strokeWidth={1.75} aria-hidden="true" />
                  </a>
                </span>
              ) : (
                <span className="muted">No fix</span>
              )}
            </Prop>
            <Prop Icon={BatteryMedium} label="Battery">
              {alert.battery !== null ? alert.battery + "%" : <span className="muted">Not sent</span>}
            </Prop>
            <Prop Icon={Thermometer} label="Temperature">
              {temperatureText(alert.temperature) || <span className="muted">Not recorded</span>}
            </Prop>
            <Prop Icon={Gauge} label="Pressure">
              {alert.pressure !== null ? formatNumber(alert.pressure) + " Pa" : <span className="muted">Not sent</span>}
            </Prop>
            {link && (
              <Prop Icon={RadioTower} label="Link">
                <LinkTag link={alert.link} />
              </Prop>
            )}
            <Prop Icon={Hash} label="Message number">
              {alert.counter !== null && alert.counter !== undefined ? alert.counter : <span className="muted">Not recorded</span>}
            </Prop>
            {alert.alert_type !== "STATUS" && (
              <Prop Icon={MessageSquare} label="Text to duty phone">
                {alert.sms_sent ? "Sent" : "Not sent"}
              </Prop>
            )}
          </dl>

          {alert.alert_type === "SUSPICIOUS" && <CameraCallout alert={alert} settings={settings} />}

          {gps ? (
            <section className="peek-map-section" aria-label="Map">
              <PeekMap alert={alert} settings={settings} update={update} theme={theme} cartoKey={cartoKey} />
              {area && (
                <p className="peek-area num">
                  <Layers size={16} strokeWidth={1.75} aria-hidden="true" />
                  {area}
                </p>
              )}
            </section>
          ) : (
            <div className="peek-nomap">
              <Building2 {...ICON} />
              <span>No GPS fix, so there is no map. {place ? place + "." : "Location unknown."}</span>
            </div>
          )}
        </article>
      </div>
    </Modal>
  );
}
