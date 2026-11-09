import { useEffect, useRef, useState } from "react";
import { Building2, ChevronDown, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { MapContainer, useMap } from "react-leaflet";
import { alertState, hasGps } from "../lib/alertMeta.js";
import { ago, placeText, studentName } from "../lib/format.js";
import { useReducedMotion } from "../lib/theme.js";
import Popover from "./Popover.jsx";
import { StatusDot, TypeTag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";
import {
  AlertZones,
  AttributionPrefix,
  BaseTiles,
  ClusterLayer,
  DEFAULT_CENTER,
  MAX_ZOOM,
  MapControls,
  SizeWatcher,
} from "./mapParts.jsx";

const ICON = { size: 16, strokeWidth: 1.75, "aria-hidden": true };

function fitTo(map, alerts, reducedMotion) {
  const points = alerts.filter(hasGps).map((a) => [a.latitude, a.longitude]);
  if (!map || !points.length) return;
  map.fitBounds(points, { maxZoom: 18, padding: [64, 64], animate: !reducedMotion });
}

/** Fits the open alerts once, on first load. Then flies to new urgent alerts when auto-zoom is on. */
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
        <Building2 {...ICON} />
        <span>
          {n} {n === 1 ? "alert has" : "alerts have"} no GPS
        </span>
        <ChevronDown {...ICON} />
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
          <PanelLeftOpen {...ICON} />
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
            <PanelLeftClose {...ICON} />
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
  // Quiet alerts first, so open ones draw on top.
  const zones = list.filter(hasGps).sort((a, b) => Number(alertState(b) === "open") - Number(alertState(a) === "open"));

  return (
    <div className="map-wrap">
      <MapContainer
        ref={setMap}
        center={DEFAULT_CENTER}
        zoom={16}
        maxZoom={MAX_ZOOM}
        zoomControl={false}
        className="map"
        zoomAnimation={!reducedMotion}
        fadeAnimation={!reducedMotion}
        markerZoomAnimation={!reducedMotion}
      >
        {configLoaded && <BaseTiles theme={theme} labels={settings.mapLabels} cartoKey={cartoKey} />}
        <AttributionPrefix />
        <SizeWatcher />
        <MapController alerts={alerts} flyTarget={flyTarget} reducedMotion={reducedMotion} />
        {zones.map((a) => (
          <AlertZones key={a.id} alert={a} sightRadius={settings.sightRadius} />
        ))}
        <ClusterLayer alerts={list} highlightedId={highlightedId} onOpen={onOpen} onHover={onHover} />
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
