import { useEffect, useRef } from "react";
import { icon as faIcon } from "@fortawesome/fontawesome-svg-core";
import { TileLayer, useMap } from "react-leaflet";
import L from "../lib/leafletSetup.js";
import "leaflet.markercluster";
import { alertState, hasGps, isOpenMedical, TYPES, typeMeta, zoneRadius } from "../lib/alertMeta.js";
import { placeText, studentName } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import { hideTooltip, showTooltip } from "../lib/tooltip.js";
import Icon from "./Icon.jsx";
import Tooltip from "./Tooltip.jsx";

export const DEFAULT_CENTER = [34.7304, -86.5861]; // Huntsville, until an alert has GPS
export const MAX_ZOOM = 20; // set on every map: clustering needs it before the tiles load

/** Shared by the Live map and the Peek map: half-step zoom and a gentler mouse wheel. */
export const MAP_OPTIONS = { zoomSnap: 0.5, wheelPxPerZoomLevel: 90, zoomControl: false };

const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>';
const CARTO_ATTRIBUTION =
  OSM_ATTRIBUTION + ' &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>';

// Markers take an HTML string, so each type icon is turned into SVG text once, when this file loads.
const ICON_SVG = new Map();
for (const type of [...Object.keys(TYPES), "OTHER"]) {
  ICON_SVG.set(type, faIcon(typeMeta(type).icon, { attributes: { "aria-hidden": "true", focusable: "false" } }).html.join(""));
}

/** Fits the map to some bounds. A short flight, or a jump when the computer asks for reduced motion. */
export function fitView(map, bounds, options, reducedMotion) {
  if (!map) return;
  if (reducedMotion) map.fitBounds(bounds, { ...options, animate: false });
  else map.flyToBounds(bounds, { ...options, duration: 0.5 });
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

/** 26 px disc in the type color, a 2 px ring (white, or the Midnight page color in dark),
    the type icon inside and a soft shadow. Acknowledged and resolved markers are smaller
    and faded. Leaflet moves the outer element with a CSS transform, so every visual effect
    (the 1.15 scale when selected, the fade) sits on the inner span, never on the element
    Leaflet moves. */
function markerIcon(alert, selected) {
  const type = TYPES[alert.alert_type] ? alert.alert_type : "OTHER";
  const quiet = alertState(alert) !== "open";
  const size = quiet ? 22 : 26;
  const classes = ["alert-marker", "alert-marker--" + typeMeta(alert.alert_type).key];
  if (quiet) classes.push("is-quiet");
  if (selected) classes.push("is-selected");
  return L.divIcon({
    className: "alert-marker-wrap",
    html: '<span class="' + classes.join(" ") + '" data-alert-id="' + alert.id + '">' + ICON_SVG.get(type) + "</span>",
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

// ---------- circles ----------

/** The circles for one alert, radius in meters. Colors come from CSS classes in map.css.
    1.5 px stroke in the type color, fill at 8%. MEDICAL, SILENT, STATUS: one circle of
    radius acc. SUSPICIOUS: a dashed circle of acc + sight radius, and a solid circle of
    acc inside it. */
function zoneSpecs(alert, sightRadius) {
  const faded = alertState(alert) === "open" ? 1 : 0.5;
  const acc = alert.accuracy || 0;
  const tag = " zone-id-" + alert.id; // lets the map test match each circle to its marker
  if (alert.alert_type === "SUSPICIOUS") {
    const specs = [
      { radius: zoneRadius(alert, sightRadius), style: { className: "zone zone--suspicious" + tag, weight: 1.5, dashArray: "6 6", opacity: faded, fillOpacity: 0.08 * faded } },
    ];
    if (acc > 0) specs.push({ radius: acc, style: { className: "zone zone--suspicious-inner" + tag, weight: 1.5, opacity: faded, fillOpacity: 0 } });
    return specs;
  }
  if (acc <= 0) return [];
  const key = typeMeta(alert.alert_type).key;
  return [{ radius: acc, style: { className: "zone zone--" + key + tag, weight: 1.5, opacity: faded, fillOpacity: 0.08 * faded } }];
}

/** Creates or updates the circles of one entry in place. Circles are only rebuilt
    when their kind changes (a new type, or accuracy appearing). */
function syncCircles(entry, alert, sightRadius, holder) {
  const specs = zoneSpecs(alert, sightRadius);
  const shape = specs.map((s) => s.style.className).join("|");
  const look = [alert.latitude, alert.longitude, ...specs.map((s) => s.radius + "/" + s.style.opacity)].join("|");
  if (entry.shape !== shape) {
    entry.circles.forEach((c) => holder.removeLayer(c));
    entry.circles = specs.map((s) => L.circle([alert.latitude, alert.longitude], { radius: s.radius, interactive: false, ...s.style }));
    entry.shape = shape;
    entry.look = look;
    entry.drawn = false;
    return;
  }
  if (entry.look === look) return; // nothing changed: no redraw
  entry.look = look;
  specs.forEach((s, i) => {
    const c = entry.circles[i];
    c.setLatLng([alert.latitude, alert.longitude]);
    c.setRadius(s.radius);
    c.setStyle({ opacity: s.style.opacity, fillOpacity: s.style.fillOpacity });
  });
}

function showCircles(entry, holder, show) {
  if (show === entry.drawn) return;
  entry.drawn = show;
  entry.circles.forEach((c) => {
    if (show) {
      holder.addLayer(c);
      if (alertState(entry.marker.alert) !== "open") c.bringToBack(); // open alerts draw on top
    } else {
      holder.removeLayer(c);
    }
  });
}

// markercluster keeps each marker's deepest cluster in __parent. The marker stands on its
// own at every zoom above that cluster's zoom. group._zoom is the zoom the clusters are drawn for.
function standsAlone(group, marker) {
  const parent = marker.__parent;
  return !parent || parent._zoom < group._zoom;
}

/** Every alert with GPS: one marker (in the cluster group) and its circles, kept per alert id.
    Positions, styles and radii are updated in place; layers are only added or removed when
    alerts appear or disappear, so a poll never redraws the map.

    Circles show only for the hovered or selected alert (activeIds), and only while its marker
    stands on its own. When markers join a cluster their circles hide at once; when a cluster
    splits, the circles come back after the split animation ends, so a circle never floats
    without its marker in the middle. */
export function AlertLayer({ alerts, sightRadius, highlightedId, selectedId = null, onOpen, onHover }) {
  const map = useMap();
  const groupRef = useRef(null);
  const holderRef = useRef(null);
  const entries = useRef(new Map()); // alert id -> { marker, key, circles, shape, drawn }
  const spread = useRef(new Set()); // ids of markers spread out by a click on a cluster
  const syncRef = useRef(() => {});
  const handlers = useRef({ onOpen, onHover });
  handlers.current = { onOpen, onHover };
  const active = useRef(new Set());
  active.current = new Set([highlightedId, selectedId].filter((id) => id !== null && id !== undefined));
  const lit = useRef([]); // inner elements that carry is-selected now
  const lightRef = useRef(() => {});

  useEffect(() => {
    const group = L.markerClusterGroup({
      animate: true,
      showCoverageOnHover: false,
      spiderfyOnMaxZoom: true,
      zoomToBoundsOnClick: true,
      maxClusterRadius: 44,
      iconCreateFunction: clusterIcon,
      spiderLegPolylineOptions: { weight: 1.5, color: "rgb(112, 109, 102)", opacity: 0.6 },
    });
    const holder = L.layerGroup(); // circles: overlay pane, default SVG renderer
    holder.addTo(map);
    map.addLayer(group);
    groupRef.current = group;
    holderRef.current = holder;

    // onlyHide: during a cluster animation, hide circles whose marker is joining a
    // cluster, but wait for the animation to end before showing new ones.
    const sync = (onlyHide = false) => {
      for (const [id, entry] of entries.current) {
        const show = active.current.has(id) && (standsAlone(group, entry.marker) || spread.current.has(id));
        if (show && onlyHide && !entry.drawn) continue;
        showCircles(entry, holder, show);
      }
    };
    syncRef.current = sync;
    const animating = () => group._inZoomAnimation > 0;
    // Registered after the cluster group, so these run after it has re-clustered.
    const onZoomEnd = () => {
      sync(true);
      lightRef.current();
    };
    const onMoveEnd = () => {
      sync(animating());
      lightRef.current();
    };
    const onAnimationEnd = () => {
      sync(false);
      lightRef.current();
    };
    map.on("zoomend", onZoomEnd);
    map.on("moveend", onMoveEnd);
    group.on("animationend", onAnimationEnd);
    group.on("spiderfied", (e) => {
      e.markers.forEach((m) => spread.current.add(m.alert.id));
      sync(false);
    });
    group.on("unspiderfied", (e) => {
      e.markers.forEach((m) => spread.current.delete(m.alert.id));
      sync(false);
    });
    group.on("clustermouseover", (e) => {
      const el = e.layer.getElement();
      if (el) showTooltip(el, { label: e.layer.getChildCount() + " alerts here", shortcut: "Click to spread them out" });
    });
    group.on("clustermouseout", () => hideTooltip());

    const current = entries.current;
    const spreadIds = spread.current;
    return () => {
      map.off("zoomend", onZoomEnd);
      map.off("moveend", onMoveEnd);
      map.removeLayer(group);
      map.removeLayer(holder);
      current.clear();
      spreadIds.clear();
      groupRef.current = null;
      holderRef.current = null;
      syncRef.current = () => {};
    };
  }, [map]);

  useEffect(() => {
    const group = groupRef.current;
    const holder = holderRef.current;
    if (!group || !holder) return;
    const wanted = new Map(alerts.filter(hasGps).map((a) => [a.id, a]));
    const remove = [];
    const add = [];
    const changed = [];
    for (const [id, entry] of entries.current) {
      if (!wanted.has(id)) {
        remove.push(entry.marker);
        showCircles(entry, holder, false);
        entries.current.delete(id);
        spread.current.delete(id);
      }
    }
    for (const a of wanted.values()) {
      const key = [a.alert_type, alertState(a), a.latitude, a.longitude].join("|");
      let entry = entries.current.get(a.id);
      if (!entry) {
        const marker = L.marker([a.latitude, a.longitude], {
          icon: markerIcon(a, active.current.has(a.id)),
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
        entry = { marker, key, circles: [], shape: null, drawn: false };
        entries.current.set(a.id, entry);
        add.push(marker);
      } else {
        entry.marker.alert = a;
        if (entry.key !== key) {
          entry.key = key;
          entry.marker.setLatLng([a.latitude, a.longitude]);
          entry.marker.setIcon(markerIcon(a, active.current.has(a.id)));
          entry.marker.setZIndexOffset(alertState(a) === "open" ? 0 : -500);
          labelElement(entry.marker);
          changed.push(entry.marker);
        }
      }
      const wasDrawn = entry.drawn;
      syncCircles(entry, a, sightRadius, holder);
      if (wasDrawn && !entry.drawn) showCircles(entry, holder, true); // rebuilt: draw again right away
    }
    if (remove.length) group.removeLayers(remove);
    if (add.length) group.addLayers(add);
    if (changed.length) group.refreshClusters(changed);
    syncRef.current(group._inZoomAnimation > 0);
    // The hovered and selected ids are read here only for new markers; the effect below keeps them current.
  }, [alerts, sightRadius]);

  // The hovered or selected alert: its marker scales up (or the cluster it is hiding in does),
  // and its circles show. Also run after zooms, because markercluster redraws marker elements.
  lightRef.current = () => {
    const group = groupRef.current;
    lit.current.forEach(({ el, entry }) => {
      el.classList.remove("is-selected");
      if (entry) entry.marker.setZIndexOffset(alertState(entry.marker.alert) === "open" ? 0 : -500);
    });
    lit.current = [];
    if (!group) return;
    for (const id of active.current) {
      const entry = entries.current.get(id);
      if (!entry) continue;
      const visible = group.getVisibleParent(entry.marker);
      if (visible === entry.marker) {
        const el = entry.marker.getElement();
        if (el && el.firstChild) {
          el.firstChild.classList.add("is-selected");
          entry.marker.setZIndexOffset(1000);
          lit.current.push({ el: el.firstChild, entry });
        }
      } else if (visible && visible.getElement() && visible.getElement().firstChild) {
        const el = visible.getElement().firstChild;
        el.classList.add("is-selected");
        lit.current.push({ el, entry: null });
      }
    }
  };
  useEffect(() => {
    lightRef.current();
    const group = groupRef.current;
    if (group) syncRef.current(group._inZoomAnimation > 0);
  }, [highlightedId, selectedId, alerts]);

  return null;
}

/** The Peek map: one marker that does nothing on click, and its circles.
    Updated in place, like the Live map. */
export function SingleAlertLayer({ alert, sightRadius }) {
  const map = useMap();
  const ref = useRef(null);

  useEffect(() => {
    const holder = L.layerGroup().addTo(map);
    const entry = { marker: null, key: null, circles: [], shape: null, drawn: false, holder };
    ref.current = entry;
    return () => {
      if (entry.marker) entry.marker.remove();
      map.removeLayer(holder);
      ref.current = null;
    };
  }, [map]);

  useEffect(() => {
    const entry = ref.current;
    if (!entry || !hasGps(alert)) return;
    const key = [alert.alert_type, alertState(alert), alert.latitude, alert.longitude].join("|");
    if (!entry.marker) {
      entry.marker = L.marker([alert.latitude, alert.longitude], { icon: markerIcon(alert, false), keyboard: false, interactive: false });
      entry.marker.addTo(map);
    } else if (entry.key !== key) {
      entry.marker.setLatLng([alert.latitude, alert.longitude]);
      entry.marker.setIcon(markerIcon(alert, false));
    }
    entry.key = key;
    entry.marker.alert = alert;
    syncCircles(entry, alert, sightRadius, entry.holder);
    showCircles(entry, entry.holder, true);
  }, [map, alert, sightRadius]);

  return null;
}

/** Floating control group, bottom right: zoom in, zoom out, fit, labels. */
export function MapControls({ map, onFit, fitLabel = "Fit all alerts", fitIcon = icons.fitAll, labels, onToggleLabels, hasKey, reducedMotion }) {
  const labelsTip = hasKey ? (labels ? "Hide map labels" : "Show map labels") : "Map labels need a CARTO key";
  return (
    <div className="map-controls" role="group" aria-label="Map controls">
      <Tooltip label="Zoom in">
        <button type="button" className="map-ctl" aria-label="Zoom in" onClick={() => map && map.zoomIn(1, { animate: !reducedMotion })}>
          <Icon icon={icons.zoomIn} />
        </button>
      </Tooltip>
      <Tooltip label="Zoom out">
        <button type="button" className="map-ctl" aria-label="Zoom out" onClick={() => map && map.zoomOut(1, { animate: !reducedMotion })}>
          <Icon icon={icons.zoomOut} />
        </button>
      </Tooltip>
      <span className="map-ctl-divider" aria-hidden="true" />
      <Tooltip label={fitLabel}>
        <button type="button" className="map-ctl" aria-label={fitLabel} onClick={onFit}>
          <Icon icon={fitIcon} />
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
          <Icon icon={icons.mapLabels} />
        </button>
      </Tooltip>
    </div>
  );
}
