import { useState } from "react";
import L from "../lib/leafletSetup.js";
import { MapContainer } from "react-leaflet";
import { alertState, hasGps, linkMeta, zoneRadius } from "../lib/alertMeta.js";
import { cameraHtml, detailsHtml } from "../lib/copyHtml.js";
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
import { Battery } from "./DevicesPage.jsx";
import Icon from "./Icon.jsx";
import Modal from "./Modal.jsx";
import { LinkTag, StatusDot, TypeTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";
import { AttributionPrefix, BaseTiles, MAP_OPTIONS, MAX_ZOOM, MapControls, SingleAlertLayer, SizeWatcher, fitView } from "./mapParts.jsx";

// How the alert panel lays out its facts.
//   "sections": a header with the actions, When and Where cards, the map, then Timeline and Fob.
//   "list":     the single list of properties used before (one row per fact, then the map).
// To go back to the old panel, set this to "list". Both layouts use the same data and buttons.
const PEEK_LAYOUT = "sections";

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

/** Review cameras (SUSPICIOUS): a plain card with the time window large, and the copy button. */
function CameraCard({ alert, settings }) {
  const cam = cameraInfo(alert, settings);
  const sameDay = formatDate(cam.start) === formatDate(cam.end);
  return (
    <section className="camera-card" aria-labelledby="camera-title">
      <div className="camera-head">
        <span className="camera-icon" aria-hidden="true">
          <Icon icon={icons.camera} size={14} />
        </span>
        <div className="camera-titles">
          <h3 id="camera-title">Review cameras</h3>
          <p className="camera-sub num">
            {settings.cameraBefore} min before to {settings.cameraAfter} min after the press
          </p>
        </div>
        <CopyButton getText={() => cam.text} getHtml={() => cameraHtml(alert, settings)} label="Copy for security" />
      </div>
      <p className="camera-window num">
        {formatTime(cam.start, settings.timeFormat)} to {formatTime(cam.end, settings.timeFormat)}
      </p>
      <div className="camera-meta num">
        <span>
          <Icon icon={icons.time} size={12} fixed />
          {sameDay ? formatDate(cam.start) : formatDate(cam.start) + " to " + formatDate(cam.end)}
        </span>
        {cam.place && (
          <span>
            <Icon icon={icons.place} size={12} fixed />
            {cam.place}
          </span>
        )}
        <span>
          <Icon icon={icons.area} size={12} fixed />
          {/* The coordinates stay out of sight here; Copy for security still includes them. */}
          {hasGps(alert) ? "Within " + zoneRadius(alert, settings.sightRadius) + " m of the GPS point" : cam.area}
        </span>
      </div>
    </section>
  );
}

function MapOrNote({ alert, settings, update, theme, cartoKey, place }) {
  const area = areaLine(alert, settings.sightRadius);
  if (!hasGps(alert)) {
    return (
      <div className="peek-nomap">
        <Icon icon={icons.floor} />
        <span>No GPS fix, so there is no map. {place ? place + "." : "Location unknown."}</span>
      </div>
    );
  }
  return (
    <section className="peek-map-section" aria-label="Map">
      <PeekMap alert={alert} settings={settings} update={update} theme={theme} cartoKey={cartoKey} />
      {area && (
        <p className="peek-area num">
          <Icon icon={icons.area} />
          {area}
        </p>
      )}
    </section>
  );
}

function Actions({ state, busy, error, onAck, onResolve }) {
  if (state === "resolved") return null;
  return (
    <div className="peek-actions">
      {state === "open" && (
        <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={onAck}>
          <Icon icon={icons.acknowledged} />
          {busy === "ack" ? "Acknowledging" : "Acknowledge"}
        </button>
      )}
      <button type="button" className="btn btn-secondary" disabled={busy !== null} onClick={onResolve}>
        <Icon icon={icons.resolve} />
        {busy === "resolve" ? "Resolving" : "Resolve"}
      </button>
      {error && (
        <p className="peek-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

// ---------- "sections" layout ----------

/** A time on the alert's timeline: just the clock when it is the same day as the press. */
function stamp(ts, pressedTs, timeFormat) {
  return formatDate(ts) === formatDate(pressedTs) ? formatTime(ts, timeFormat) : formatDateTime(ts, timeFormat, false);
}

/** The latitude and longitude, hidden until asked for: most people only need the map link. */
function GpsPoint({ alert }) {
  const [shown, setShown] = useState(false);
  return (
    <>
      <button type="button" className="link-btn" aria-expanded={shown} onClick={() => setShown((s) => !s)}>
        {shown ? "Hide GPS point" : "Show GPS point"}
      </button>
      {shown && (
        <span className="gps-point">
          {coords(alert)}
          {alert.accuracy !== null ? ", within " + alert.accuracy + " m" : ""}
        </span>
      )}
    </>
  );
}

function Step({ done, label, children }) {
  return (
    <li className={"tl-step" + (done ? " is-done" : "")}>
      <span className="tl-dot" aria-hidden="true" />
      <span className="tl-label">{label}</span>
      <span className="tl-value num">{children}</span>
    </li>
  );
}

function Kv({ label, children }) {
  return (
    <div className="kv-row">
      <dt>{label}</dt>
      <dd className="num">{children}</dd>
    </div>
  );
}

function SectionsBody({ alert, state, settings, update, theme, cartoKey, nowServer, actions }) {
  const gps = hasGps(alert);
  const place = placeText(alert);
  const link = linkMeta(alert.link);
  const tf = settings.timeFormat;
  return (
    <article className="peek-page peek-page--sections">
      <header className="peek-head">
        <div className="peek-head-main">
          <h2 id="peek-title">{studentName(alert)}</h2>
          <div className="peek-meta">
            <TypeTag type={alert.alert_type} />
            <StatusDot state={state} />
            <span className="peek-id">{alert.device_id}</span>
          </div>
        </div>
        {actions}
      </header>

      <div className="peek-facts">
        <section className="fact" aria-label="When">
          <div className="fact-label">
            <Icon icon={icons.time} size={12} fixed />
            Pressed
          </div>
          <div className="fact-main num">{formatTime(alert.timestamp, tf)}</div>
          <div className="fact-sub num">
            <span>{formatDate(alert.timestamp)}</span>
            <span className="muted">{ago(nowServer - alert.timestamp)}</span>
          </div>
        </section>
        <section className="fact" aria-label="Where">
          <div className="fact-label">
            <Icon icon={icons.place} size={12} fixed />
            Place
          </div>
          <div className="fact-main">{place || <span className="muted">Unknown</span>}</div>
          <div className="fact-sub num">
            {gps ? (
              <>
                <a href={googleMapsUrl(alert)} target="_blank" rel="noopener noreferrer">
                  Open in Google Maps
                  <Icon icon={icons.externalLink} size={12} />
                </a>
                <GpsPoint alert={alert} />
              </>
            ) : alert.floor !== null && alert.floor !== undefined ? (
              <span>Floor worked out from air pressure, no GPS fix</span>
            ) : (
              <span className="muted">No GPS fix and no floor</span>
            )}
          </div>
        </section>
      </div>

      {alert.alert_type === "SUSPICIOUS" && <CameraCard alert={alert} settings={settings} />}

      <MapOrNote alert={alert} settings={settings} update={update} theme={theme} cartoKey={cartoKey} place={place} />

      <div className="peek-columns">
        <section className="peek-section" aria-labelledby="tl-title">
          <h3 id="tl-title" className="peek-section-title">
            Timeline
          </h3>
          <ol className="timeline">
            <Step done label="Pressed">
              {formatTime(alert.timestamp, tf)}
            </Step>
            {alert.alert_type !== "STATUS" && (
              <Step done={!!alert.sms_sent} label="Text to duty phone">
                {alert.sms_sent ? "Sent" : <span className="muted">Not sent</span>}
              </Step>
            )}
            <Step done={!!alert.acknowledged} label="Acknowledged">
              {alert.acknowledged && alert.acknowledged_at ? stamp(alert.acknowledged_at, alert.timestamp, tf) : <span className="muted">Not yet</span>}
            </Step>
            <Step done={!!alert.resolved} label="Resolved">
              {alert.resolved && alert.resolved_at ? stamp(alert.resolved_at, alert.timestamp, tf) : <span className="muted">Not yet</span>}
            </Step>
          </ol>
        </section>
        <section className="peek-section" aria-labelledby="fob-title">
          <h3 id="fob-title" className="peek-section-title">
            Fob
          </h3>
          <dl className="kv">
            <Kv label="Battery">{alert.battery !== null && alert.battery !== undefined ? <Battery value={alert.battery} /> : <span className="muted">Not sent</span>}</Kv>
            <Kv label="Link">{link ? <LinkTag link={alert.link} /> : <span className="muted">Not known</span>}</Kv>
            <Kv label="Floor">
              {alert.floor !== null && alert.floor !== undefined ? alert.floor : <span className="muted">{gps ? "Not needed, GPS fix" : "Not worked out"}</span>}
            </Kv>
            <Kv label="Pressure">{alert.pressure !== null && alert.pressure !== undefined ? formatNumber(alert.pressure) + " Pa" : <span className="muted">Not sent</span>}</Kv>
            <Kv label="Temperature">{temperatureText(alert.temperature) || <span className="muted">Not recorded</span>}</Kv>
            <Kv label="Message number">
              {alert.counter !== null && alert.counter !== undefined ? alert.counter : <span className="muted">Not recorded</span>}
            </Kv>
          </dl>
        </section>
      </div>
    </article>
  );
}

// ---------- "list" layout (the panel before the sections) ----------

function ListBody({ alert, state, settings, update, theme, cartoKey, nowServer, actions }) {
  const gps = hasGps(alert);
  const place = placeText(alert);
  const link = linkMeta(alert.link);
  return (
    <article className="peek-page">
      <div className="peek-title-row">
        <h2 id="peek-title">{studentName(alert)}</h2>
        <span className="peek-id">{alert.device_id}</span>
        <span className="peek-title-meta">
          <TypeTag type={alert.alert_type} />
          <StatusDot state={state} />
        </span>
      </div>
      {actions}
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
      {alert.alert_type === "SUSPICIOUS" && <CameraCard alert={alert} settings={settings} />}
      <MapOrNote alert={alert} settings={settings} update={update} theme={theme} cartoKey={cartoKey} place={place} />
    </article>
  );
}

export default function AlertPeek({ alert, crumb = "Live", settings, update, theme, cartoKey, nowServer, onClose, onAck, onResolve, returnFocus }) {
  const [busy, setBusy] = useState(null); // "ack" or "resolve"
  const [error, setError] = useState(null);
  const state = alertState(alert);

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

  const actions = (
    <Actions state={state} busy={busy} error={error} onAck={() => run("ack", onAck)} onResolve={() => run("resolve", onResolve)} />
  );
  const Body = PEEK_LAYOUT === "list" ? ListBody : SectionsBody;

  return (
    <Modal onClose={onClose} labelledBy="peek-title" className="peek" returnFocus={returnFocus}>
      <div className="peek-strip">
        <nav className="crumbs" aria-label="Breadcrumb">
          <span>{crumb}</span>
          <span className="crumb-sep" aria-hidden="true">
            /
          </span>
          <span className="crumb-current">{studentName(alert)}</span>
        </nav>
        <div className="peek-strip-actions">
          <CopyButton getText={() => detailsText(alert, settings)} getHtml={() => detailsHtml(alert, settings)} label="Copy details" variant="ghost" />
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
        <Body alert={alert} state={state} settings={settings} update={update} theme={theme} cartoKey={cartoKey} nowServer={nowServer} actions={actions} />
      </div>
    </Modal>
  );
}
