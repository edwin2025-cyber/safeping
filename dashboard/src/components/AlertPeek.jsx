import { useState } from "react";
import L from "../lib/leafletSetup.js";
import { MapContainer } from "react-leaflet";
import { alertState, hasGps, linkMeta, zoneRadius } from "../lib/alertMeta.js";
import { batteryIcon, icons } from "../lib/icons.js";
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
import Icon from "./Icon.jsx";
import Modal from "./Modal.jsx";
import { LinkTag, StatusDot, TypeTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";
import { AttributionPrefix, BaseTiles, MAP_OPTIONS, MAX_ZOOM, MapControls, SingleAlertLayer, SizeWatcher, fitView } from "./mapParts.jsx";

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
        {...MAP_OPTIONS}
        scrollWheelZoom={false}
        className="map"
        zoomAnimation={!reducedMotion}
        fadeAnimation={!reducedMotion}
        markerZoomAnimation={!reducedMotion}
      >
        <BaseTiles theme={theme} labels={settings.mapLabels} cartoKey={cartoKey} />
        <AttributionPrefix />
        <SizeWatcher />
        <SingleAlertLayer alert={alert} sightRadius={settings.sightRadius} />
      </MapContainer>
      <MapControls
        map={map}
        onFit={() => fitView(map, boundsFor(alert, settings.sightRadius), { maxZoom: 18 }, reducedMotion)}
        fitLabel="Center on the alert"
        fitIcon={icons.center}
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
        <Icon icon={icons.camera} className="callout-icon" />
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
              <Icon icon={icons.openFullPage} />
            </button>
          </Tooltip>
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
            <h2 id="peek-title">{studentName(alert)}</h2>
            <span className="peek-id">{alert.device_id}</span>
            <TypeTag type={alert.alert_type} />
            <StatusDot state={state} />
          </div>

          {state !== "resolved" && (
            <div className="peek-actions">
              {state === "open" && (
                <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => run("ack", onAck)}>
                  <Icon icon={icons.acknowledged} />
                  {busy === "ack" ? "Acknowledging" : "Acknowledge"}
                </button>
              )}
              <button type="button" className="btn btn-secondary" disabled={busy !== null} onClick={() => run("resolve", onResolve)}>
                <Icon icon={icons.resolve} />
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
            <Prop icon={icons.time} label="Pressed">
              {formatDateTime(alert.timestamp, settings.timeFormat)} <span className="muted">({ago(nowServer - alert.timestamp)})</span>
            </Prop>
            <Prop icon={icons.place} label="Place">
              {place || <span className="muted">Unknown</span>}
            </Prop>
            <Prop icon={icons.floor} label="Floor">
              {alert.floor !== null ? alert.floor : <span className="muted">{gps ? "Not needed, GPS fix" : "Not worked out"}</span>}
            </Prop>
            <Prop icon={icons.gps} label="GPS">
              {gps ? (
                <span className="prop-gps">
                  <span>
                    {coords(alert)}
                    {alert.accuracy !== null ? ", within " + alert.accuracy + " m" : ""}
                  </span>
                  <a href={googleMapsUrl(alert)} target="_blank" rel="noopener noreferrer">
                    Open in Google Maps
                    <Icon icon={icons.externalLink} size={12} />
                  </a>
                </span>
              ) : (
                <span className="muted">No fix</span>
              )}
            </Prop>
            <Prop icon={batteryIcon(alert.battery)} label="Battery">
              {alert.battery !== null ? alert.battery + "%" : <span className="muted">Not sent</span>}
            </Prop>
            <Prop icon={icons.temperature} label="Temperature">
              {temperatureText(alert.temperature) || <span className="muted">Not recorded</span>}
            </Prop>
            <Prop icon={icons.pressure} label="Pressure">
              {alert.pressure !== null ? formatNumber(alert.pressure) + " Pa" : <span className="muted">Not sent</span>}
            </Prop>
            {link && (
              <Prop icon={link.icon} label="Link">
                <LinkTag link={alert.link} />
              </Prop>
            )}
            <Prop icon={icons.messageNumber} label="Message number">
              {alert.counter !== null && alert.counter !== undefined ? alert.counter : <span className="muted">Not recorded</span>}
            </Prop>
            {alert.alert_type !== "STATUS" && (
              <Prop icon={icons.text} label="Text to duty phone">
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
                  <Icon icon={icons.area} />
                  {area}
                </p>
              )}
            </section>
          ) : (
            <div className="peek-nomap">
              <Icon icon={icons.floor} />
              <span>No GPS fix, so there is no map. {place ? place + "." : "Location unknown."}</span>
            </div>
          )}
        </article>
      </div>
    </Modal>
  );
}
