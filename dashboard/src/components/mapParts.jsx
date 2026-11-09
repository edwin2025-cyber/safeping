import { useEffect, useRef } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import { LocateFixed, Maximize, Minus, Plus, Type } from "lucide-react";
import { Circle, TileLayer, useMap } from "react-leaflet";
import L from "../lib/leafletSetup.js";
import "leaflet.markercluster";
import { alertState, hasGps, isOpenMedical, TYPES, typeMeta, zoneRadius } from "../lib/alertMeta.js";
import { placeText, studentName } from "../lib/format.js";
import { hideTooltip, showTooltip } from "../lib/tooltip.js";
import Tooltip from "./Tooltip.jsx";

export const DEFAULT_CENTER = [34.7304, -86.5861]; // Huntsville, until an alert has GPS
export const MAX_ZOOM = 20; // set on every map: clustering needs it before the tiles load

const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>';
const CARTO_ATTRIBUTION =
  OSM_ATTRIBUTION + ' &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>';

// Markers take an HTML string, so the type icons are drawn to SVG text once,
// when this file loads (never during a React render).
const ICON_SVG = new Map();
for (const type of [...Object.keys(TYPES), "OTHER"]) {
  for (const small of [false, true]) {
    const { Icon } = typeMeta(type);
    const holder = document.createElement("div");
    const root = createRoot(holder);
    flushSync(() => root.render(<Icon size={small ? 12 : 16} strokeWidth={1.75} aria-hidden="true" focusable="false" />));
    ICON_SVG.set(type + "|" + small, holder.innerHTML);
    root.unmount();
  }
}

/** CARTO raster basemaps when a key is set, otherwise OpenStreetMap (dimmed in dark mode). */
export function BaseTiles({ theme, labels, cartoKey }) {
  if (cartoKey) {
    const style = theme === "dark" ? (labels ? "dark_all" : "dark_nolabels") : labels ? "light_all" : "light_nolabels";
    const url =
      "https://{s}.basemaps.cartocdn.com/rastertiles/" + style + "/{z}/{x}/{y}{r}.png?key=" + encodeURIComponent(cartoKey);
    return <TileLayer key={url} url={url} subdomains="abcd" maxNativeZoom={18} maxZoom={MAX_ZOOM} attribution={CARTO_ATTRIBUTION} />;
  }
  const url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  return <TileLayer key={url} url={url} maxNativeZoom={19} maxZoom={MAX_ZOOM} attribution={OSM_ATTRIBUTION} className="osm-tiles" />;
}

/** Plain attribution prefix: just the Leaflet link, no flag. */
export function AttributionPrefix() {
  const map = useMap();
  useEffect(() => {
    if (map.attributionControl) {
      map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
    }
  }, [map]);
  return null;
}

/** Leaflet measures its box once. Tell it when the box changes size. */
export function SizeWatcher() {
  const map = useMap();
  useEffect(() => {
    if (!window.ResizeObserver) return undefined;
    const observer = new ResizeObserver(() => map.invalidateSize({ animate: false }));
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  return null;
}

function markerLabel(alert) {
  const state = alertState(alert);
  return typeMeta(alert.alert_type).label + ": " + studentName(alert) + (state === "open" ? "" : " (" + state + ")");
}

/** 28 px circle in the type's bold color, white ring, type icon inside.
    Acknowledged and resolved markers are smaller and faded. */
function markerIcon(alert, highlighted) {
  const type = TYPES[alert.alert_type] ? alert.alert_type : "OTHER";
  const quiet = alertState(alert) !== "open";
  const size = quiet ? 22 : 28;
  const classes = ["alert-marker", "alert-marker--" + typeMeta(alert.alert_type).color];
  if (quiet) classes.push("is-quiet");
  if (highlighted) classes.push("is-highlighted");
  return L.divIcon({
    className: "alert-marker-wrap",
    html: '<span class="' + classes.join(" ") + '">' + ICON_SVG.get(type + "|" + quiet) + "</span>",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

/** Neutral cluster with a count. The ring is red when an open MEDICAL is inside. */
function clusterIcon(cluster) {
  const children = cluster.getAllChildMarkers();
  const medical = children.some((m) => m.alert && isOpenMedical(m.alert));
  const n = cluster.getChildCount();
  return L.divIcon({
    className: "cluster-wrap",
    html:
      '<span class="cluster' + (medical ? " cluster--medical" : "") + '">' + n +
      '<span class="visually-hidden"> alerts here' + (medical ? ", one is an open medical alert" : "") + "</span></span>",
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
}

function labelElement(marker) {
  const el = marker.getElement();
  if (el && marker.alert) el.setAttribute("aria-label", markerLabel(marker.alert) + ". Open details");
}

/** Markers in a cluster layer. Managed by hand (not one React component per
    marker) so clusters update cleanly when alerts change. */
export function ClusterLayer({ alerts, highlightedId, onOpen, onHover }) {
  const map = useMap();
  const groupRef = useRef(null);
  const markers = useRef(new Map()); // alert id -> { marker, key }
  const handlers = useRef({ onOpen, onHover });
  handlers.current = { onOpen, onHover };
  const lit = useRef({ id: null, parent: null });

  useEffect(() => {
    const group = L.markerClusterGroup({
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      zoomToBoundsOnClick: true,
      maxClusterRadius: 44,
      iconCreateFunction: clusterIcon,
      spiderLegPolylineOptions: { weight: 1.5, color: "rgb(107, 110, 118)", opacity: 0.6 },
    });
    group.on("clustermouseover", (e) => {
      const el = e.layer.getElement();
      if (el) showTooltip(el, { label: e.layer.getChildCount() + " alerts here", shortcut: "Click to spread them out" });
    });
    group.on("clustermouseout", () => hideTooltip());
    map.addLayer(group);
    groupRef.current = group;
    const current = markers.current;
    return () => {
      map.removeLayer(group);
      current.clear();
      groupRef.current = null;
    };
  }, [map]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    const wanted = new Map(alerts.filter(hasGps).map((a) => [a.id, a]));
    const remove = [];
    const add = [];
    const changed = [];
    for (const [id, entry] of markers.current) {
      if (!wanted.has(id)) {
        remove.push(entry.marker);
        markers.current.delete(id);
      }
    }
    for (const a of wanted.values()) {
      const key = [a.alert_type, alertState(a), a.latitude, a.longitude].join("|");
      const entry = markers.current.get(a.id);
      if (!entry) {
        const marker = L.marker([a.latitude, a.longitude], {
          icon: markerIcon(a, a.id === highlightedId),
          keyboard: true,
          zIndexOffset: alertState(a) === "open" ? 0 : -500,
        });
        marker.alert = a;
        marker.on("click", () => handlers.current.onOpen(marker.alert.id));
        marker.on("mouseover", () => {
          handlers.current.onHover(marker.alert.id);
          const el = marker.getElement();
          if (el) showTooltip(el, { label: markerLabel(marker.alert), shortcut: placeText(marker.alert) || undefined });
        });
        marker.on("mouseout", () => {
          handlers.current.onHover(null);
          hideTooltip();
        });
        marker.on("add", () => labelElement(marker));
        markers.current.set(a.id, { marker, key });
        add.push(marker);
      } else {
        entry.marker.alert = a;
        if (entry.key !== key) {
          entry.key = key;
          entry.marker.setLatLng([a.latitude, a.longitude]);
          entry.marker.setIcon(markerIcon(a, a.id === highlightedId));
          entry.marker.setZIndexOffset(alertState(a) === "open" ? 0 : -500);
          labelElement(entry.marker);
          changed.push(entry.marker);
        }
      }
    }
    if (remove.length) group.removeLayers(remove);
    if (add.length) group.addLayers(add);
    if (changed.length) group.refreshClusters(changed);
    // highlightedId is read here only for new markers; the effect below keeps it current.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alerts]);

  // Hovering a row lights up its marker, or the cluster it is hiding in.
  useEffect(() => {
    const group = groupRef.current;
    const prev = lit.current;
    if (prev.parent) prev.parent.classList.remove("is-highlighted");
    const prevEntry = prev.id !== null ? markers.current.get(prev.id) : null;
    if (prevEntry) {
      const el = prevEntry.marker.getElement();
      if (el && el.firstChild) el.firstChild.classList.remove("is-highlighted");
      prevEntry.marker.setZIndexOffset(alertState(prevEntry.marker.alert) === "open" ? 0 : -500);
    }
    lit.current = { id: null, parent: null };
    const entry = highlightedId !== null ? markers.current.get(highlightedId) : null;
    if (!entry || !group) return;
    const visible = group.getVisibleParent(entry.marker);
    if (visible === entry.marker) {
      const el = entry.marker.getElement();
      if (el && el.firstChild) el.firstChild.classList.add("is-highlighted");
      entry.marker.setZIndexOffset(1000);
      lit.current = { id: highlightedId, parent: null };
    } else if (visible && visible.getElement()) {
      const el = visible.getElement().firstChild;
      if (el) el.classList.add("is-highlighted");
      lit.current = { id: highlightedId, parent: el };
    }
  }, [highlightedId, alerts]);

  return null;
}

/** One marker that does nothing on click, for the peek map. */
export function StaticMarker({ alert }) {
  const map = useMap();
  const alertRef = useRef(alert);
  alertRef.current = alert;
  const key = [alert.id, alert.alert_type, alertState(alert), alert.latitude, alert.longitude].join("|");
  useEffect(() => {
    const a = alertRef.current;
    const marker = L.marker([a.latitude, a.longitude], { icon: markerIcon(a, false), keyboard: false, interactive: false });
    marker.addTo(map);
    return () => marker.remove();
  }, [map, key]);
  return null;
}

/** One circle. react-leaflet hands top-level props to Leaflet when the circle
    is created (className only works there), and pathOptions on later changes. */
function Zone({ center, radius, style }) {
  return <Circle center={center} radius={radius} interactive={false} {...style} pathOptions={style} />;
}

/** Circles for one alert, radius in meters. Colors come from CSS classes in map.css. */
export function AlertZones({ alert, sightRadius }) {
  if (!hasGps(alert)) return null;
  const center = [alert.latitude, alert.longitude];
  const color = typeMeta(alert.alert_type).color;
  const faded = alertState(alert) === "open" ? 1 : 0.5;
  const acc = alert.accuracy || 0;

  if (alert.alert_type === "SUSPICIOUS") {
    return (
      <>
        <Zone
          center={center}
          radius={zoneRadius(alert, sightRadius)}
          style={{ className: "zone zone--sight", weight: 2, dashArray: "6 6", opacity: faded, fillOpacity: 0.12 * faded }}
        />
        {acc > 0 && (
          <Zone center={center} radius={acc} style={{ className: "zone zone--yellow-inner", weight: 1.5, opacity: faded, fillOpacity: 0 }} />
        )}
      </>
    );
  }
  if (acc <= 0) return null;
  return (
    <Zone
      center={center}
      radius={acc}
      style={{ className: "zone zone--" + color, weight: 2, opacity: faded, fillOpacity: 0.12 * faded }}
    />
  );
}

/** Floating control group, bottom right: zoom in, zoom out, fit, labels. */
export function MapControls({ map, onFit, fitLabel = "Fit all alerts", FitIcon = Maximize, labels, onToggleLabels, hasKey, reducedMotion }) {
  const ICON = { size: 16, strokeWidth: 1.75, "aria-hidden": true };
  const labelsTip = hasKey ? (labels ? "Hide map labels" : "Show map labels") : "Map labels need a CARTO key";
  return (
    <div className="map-controls" role="group" aria-label="Map controls">
      <Tooltip label="Zoom in">
        <button type="button" className="map-ctl" aria-label="Zoom in" onClick={() => map && map.zoomIn(1, { animate: !reducedMotion })}>
          <Plus {...ICON} />
        </button>
      </Tooltip>
      <Tooltip label="Zoom out">
        <button type="button" className="map-ctl" aria-label="Zoom out" onClick={() => map && map.zoomOut(1, { animate: !reducedMotion })}>
          <Minus {...ICON} />
        </button>
      </Tooltip>
      <span className="map-ctl-divider" aria-hidden="true" />
      <Tooltip label={fitLabel}>
        <button type="button" className="map-ctl" aria-label={fitLabel} onClick={onFit}>
          <FitIcon {...ICON} />
        </button>
      </Tooltip>
      <Tooltip label={labelsTip}>
        <button
          type="button"
          className="map-ctl"
          aria-label={labelsTip}
          aria-pressed={hasKey ? labels : undefined}
          aria-disabled={hasKey ? undefined : true}
          onClick={() => hasKey && onToggleLabels()}
        >
          <Type {...ICON} />
        </button>
      </Tooltip>
    </div>
  );
}

export { LocateFixed };
