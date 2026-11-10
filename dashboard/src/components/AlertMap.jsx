import { useEffect, useRef, useState } from "react";
import { MapContainer, useMap } from "react-leaflet";
import L from "../lib/leafletSetup.js";
import { alertState, hasGps } from "../lib/alertMeta.js";
import { ago, placeText, studentName } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import { useReducedMotion } from "../lib/theme.js";
import Icon from "./Icon.jsx";
import Popover from "./Popover.jsx";
import { StatusDot, TypeTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";
import { AlertLayer, AttributionPrefix, BaseTiles, DEFAULT_CENTER, MAP_OPTIONS, MAX_ZOOM, MapControls, SizeWatcher, fitView } from "./mapParts.jsx";

const FIT = { maxZoom: 18, padding: [64, 64] };

/** Fits the map to these alerts. No animation for the first fit; Fit all flies for 0.5 s. */
function fitTo(map, alerts, reducedMotion) {
  const points = alerts.filter(hasGps).map((a) => [a.latitude, a.longitude]);
  if (!map || !points.length) return;
  fitView(map, L.latLngBounds(points), FIT, reducedMotion);
}

/** Fits the open alerts once, on first load. Then flies to new urgent alerts when auto-zoom is on.
    A poll never moves the map. */
function MapController({ alerts, flyTarget, reducedMotion }) {
  const map = useMap();
  const fitted = useRef(false);

  useEffect(() => {
    if (fitted.current || alerts === null) return;
    fitted.current = true;
    const open = alerts.filter((a) => alertState(a) === "open" && hasGps(a));
    fitTo(map, open.length ? open : alerts, true);
  }, [alerts, map]);

  useEffect(() => {
    if (!flyTarget) return;
    const target = [flyTarget.latitude, flyTarget.longitude];
    const zoom = Math.max(map.getZoom(), 17);
    if (reducedMotion) map.setView(target, zoom, { animate: false });
    else map.flyTo(target, zoom, { duration: 1.2 });
  }, [flyTarget, map, reducedMotion]);

  return null;
}

/** "2 alerts have no GPS". Click it to list them. */
function IndoorNote({ alerts, onOpen }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const n = alerts.length;
  return (
    <>
      <button
        ref={ref}
        type="button"
        className="map-chip"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <Icon icon={icons.floor} />
        <span>
          {n} {n === 1 ? "alert has" : "alerts have"} no GPS
        </span>
        <Icon icon={icons.chevronDown} size={12} />
      </button>
      <Popover anchor={ref.current} open={open} onClose={() => setOpen(false)} label="Alerts with no GPS" className="popover--alerts">
        <div className="popover-title">No GPS fix</div>
        {alerts.map((a) => (
          <button
            key={a.id}
            type="button"
            role="menuitem"
            className="menu-item menu-alert"
            onClick={() => {
              setOpen(false);
              onOpen(a.id);
            }}
          >
            <TypeTag type={a.alert_type} />
            <span className="menu-alert-name">{studentName(a)}</span>
            <span className="menu-alert-place">{placeText(a) || "Unknown"}</span>
          </button>
        ))}
      </Popover>
    </>
  );
}

/** Map view: the alert list floats over the map and can be hidden. */
function ListPanel({ alerts, collapsed, onToggle, nowServer, highlightedId, onOpen, onHover, registerFocus }) {
  if (collapsed) {
    return (
      <Tooltip label="Show list">
        <button type="button" className="map-chip" onClick={onToggle} aria-label={"Show list, " + alerts.length + " alerts"}>
          <Icon icon={icons.expand} />
          <span>Alerts</span>
          <span className="map-chip-count num">{alerts.length}</span>
        </button>
      </Tooltip>
    );
  }
  return (
    <section className="map-panel" aria-labelledby="map-panel-title">
      <header className="map-panel-head">
        <h2 id="map-panel-title">Alerts</h2>
        <span className="map-panel-count num">{alerts.length}</span>
        <Tooltip label="Hide list">
          <button type="button" className="icon-btn icon-btn-sm" aria-label="Hide list" onClick={onToggle}>
            <Icon icon={icons.collapse} />
          </button>
        </Tooltip>
      </header>
      {alerts.length === 0 ? (
        <p className="map-panel-empty">No alerts in this view.</p>
      ) : (
        <ul className="map-panel-list">
          {alerts.map((a) => (
            <li key={a.id}>
              <button
                ref={(node) => registerFocus(a.id, node)}
                type="button"
                className={"panel-row" + (a.id === highlightedId ? " is-hovered" : "") + (a.alert_type === "MEDICAL" && alertState(a) === "open" ? " is-medical-open" : "")}
                onClick={() => onOpen(a.id)}
                onMouseEnter={() => onHover(a.id)}
                onMouseLeave={() => onHover(null)}
                onFocus={() => onHover(a.id)}
                onBlur={() => onHover(null)}
                aria-haspopup="dialog"
              >
                <span className="panel-row-top">
                  <span className="panel-name">{studentName(a)}</span>
                  <span className="panel-time num">{ago(nowServer - a.timestamp)}</span>
                </span>
                <span className="panel-row-bottom">
                  <TypeTag type={a.alert_type} />
                  <span className="panel-place">{placeText(a) || "Unknown"}</span>
                  <StatusDot alert={a} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The Live map: tiles, circles, clustered markers, the control group, the
    "no GPS" note and, in Map view, the floating list. */
export default function AlertMap({
  alerts,
  theme,
  settings,
  update,
  cartoKey,
  configLoaded,
  highlightedId,
  onHover,
  onOpen,
  flyTarget,
  withPanel,
  panelCollapsed,
  onTogglePanel,
  nowServer,
  registerFocus,
}) {
  const [map, setMap] = useState(null);
  const reducedMotion = useReducedMotion();
  const list = alerts || [];
  const noGps = list.filter((a) => !hasGps(a));

  return (
    <div className="map-wrap">
      <MapContainer
        ref={setMap}
        center={DEFAULT_CENTER}
        zoom={16}
        maxZoom={MAX_ZOOM}
        {...MAP_OPTIONS}
        className="map"
        zoomAnimation={!reducedMotion}
        fadeAnimation={!reducedMotion}
        markerZoomAnimation={!reducedMotion}
      >
        {configLoaded && <BaseTiles theme={theme} labels={settings.mapLabels} cartoKey={cartoKey} />}
        <AttributionPrefix />
        <SizeWatcher />
        <MapController alerts={alerts} flyTarget={flyTarget} reducedMotion={reducedMotion} />
        <AlertLayer alerts={list} sightRadius={settings.sightRadius} highlightedId={highlightedId} onOpen={onOpen} onHover={onHover} />
      </MapContainer>

      <div className="map-overlay-tl">
        {withPanel && (
          <ListPanel
            alerts={list}
            collapsed={panelCollapsed}
            onToggle={onTogglePanel}
            nowServer={nowServer}
            highlightedId={highlightedId}
            onOpen={onOpen}
            onHover={onHover}
            registerFocus={registerFocus}
          />
        )}
        {noGps.length > 0 && <IndoorNote alerts={noGps} onOpen={onOpen} />}
      </div>

      <MapControls
        map={map}
        onFit={() => fitTo(map, list, reducedMotion)}
        labels={settings.mapLabels}
        onToggleLabels={() => update({ mapLabels: !settings.mapLabels })}
        hasKey={!!cartoKey}
        reducedMotion={reducedMotion}
      />
    </div>
  );
}
