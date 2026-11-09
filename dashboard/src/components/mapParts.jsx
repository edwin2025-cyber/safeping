import { useEffect } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import L from "leaflet";
import { Circle, Marker, TileLayer, useMap } from "react-leaflet";
import { hasGps, TYPES, typeMeta, zoneRadius } from "../lib/alertMeta.js";
import { studentName } from "../lib/format.js";

// Leaflet markers take an HTML string, so the few type icons are drawn to SVG
// text once, when this file loads (never during a React render).
const ICON_SVG = new Map();
for (const type of [...Object.keys(TYPES), "OTHER"]) {
  for (const small of [false, true]) {
    const { Icon } = typeMeta(type);
    const holder = document.createElement("div");
    const root = createRoot(holder);
    flushSync(() =>
      root.render(<Icon size={small ? 12 : 16} strokeWidth={2.25} aria-hidden="true" focusable="false" />),
    );
    ICON_SVG.set(type + "|" + small, holder.innerHTML);
    root.unmount();
  }
}

export const DEFAULT_CENTER = [34.7304, -86.5861]; // Huntsville, until an alert has GPS

const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>';
const CARTO_ATTRIBUTION =
  OSM_ATTRIBUTION + ' &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>';

/** CARTO raster basemaps when a key is set, otherwise OpenStreetMap (dimmed in dark mode). */
export function BaseTiles({ theme, labels, cartoKey }) {
  if (cartoKey) {
    const style = theme === "dark" ? (labels ? "dark_all" : "dark_nolabels") : labels ? "light_all" : "light_nolabels";
    const url =
      "https://{s}.basemaps.cartocdn.com/rastertiles/" + style + "/{z}/{x}/{y}{r}.png?key=" + encodeURIComponent(cartoKey);
    return (
      <TileLayer
        key={url}
        url={url}
        subdomains="abcd"
        maxNativeZoom={18}
        maxZoom={20}
        attribution={CARTO_ATTRIBUTION}
      />
    );
  }
  const url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  return <TileLayer key={url} url={url} maxZoom={19} attribution={OSM_ATTRIBUTION} className="osm-tiles" />;
}

/** Keeps the attribution plain: no flag, just the Leaflet link. */
export function AttributionPrefix() {
  const map = useMap();
  useEffect(() => {
    if (map.attributionControl) {
      map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
    }
  }, [map]);
  return null;
}

/** Leaflet measures its box once. Tell it when the box changes size (sidebar toggle, window resize). */
export function SizeWatcher() {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    if (!window.ResizeObserver) return undefined;
    const observer = new ResizeObserver(() => map.invalidateSize({ animate: false }));
    observer.observe(el);
    return () => observer.disconnect();
  }, [map]);
  return null;
}

const iconCache = new Map();

/** Round marker in the type's bold color, type icon in on-bold, 2 px surface ring (CSS). */
export function markerIcon(type, acknowledged, highlighted) {
  const key = type + "|" + acknowledged + "|" + highlighted;
  if (iconCache.has(key)) return iconCache.get(key);
  const meta = typeMeta(type);
  const size = acknowledged ? 22 : 30;
  const svg = ICON_SVG.get((TYPES[type] ? type : "OTHER") + "|" + acknowledged);
  const classes = [
    "alert-marker",
    "alert-marker--" + meta.color,
    acknowledged ? "is-acknowledged" : "",
    highlighted ? "is-highlighted" : "",
  ].join(" ");
  const icon = L.divIcon({
    className: "alert-marker-wrap",
    html: '<span class="' + classes + '" style="width:' + size + "px;height:" + size + 'px">' + svg + "</span>",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
  iconCache.set(key, icon);
  return icon;
}

/** One circle. react-leaflet hands the top-level props to Leaflet when the circle
    is created (className only works there), and pathOptions on later changes. */
function Zone({ center, radius, style }) {
  return <Circle center={center} radius={radius} interactive={false} {...style} pathOptions={style} />;
}

/** Circles for one alert. Radius is in meters. Colors come from CSS classes in map.css. */
export function AlertZones({ alert, sightRadius }) {
  if (!hasGps(alert)) return null;
  const center = [alert.latitude, alert.longitude];
  const color = typeMeta(alert.alert_type).color;
  const faded = alert.acknowledged ? 0.5 : 1;
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
          <Zone
            center={center}
            radius={acc}
            style={{ className: "zone zone--yellow-inner", weight: 1.5, opacity: faded, fillOpacity: 0 }}
          />
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

export function AlertMarker({ alert, highlighted = false, onOpen, onHover }) {
  if (!hasGps(alert)) return null;
  const meta = typeMeta(alert.alert_type);
  return (
    <Marker
      position={[alert.latitude, alert.longitude]}
      icon={markerIcon(alert.alert_type, alert.acknowledged, highlighted)}
      zIndexOffset={highlighted ? 1000 : alert.acknowledged ? -500 : 0}
      title={meta.label + ": " + studentName(alert) + (alert.acknowledged ? " (acknowledged)" : "")}
      keyboard={!!onOpen}
      interactive={!!onOpen}
      eventHandlers={
        onOpen
          ? {
              click: () => onOpen(alert.id),
              mouseover: () => onHover && onHover(alert.id),
              mouseout: () => onHover && onHover(null),
            }
          : undefined
      }
    />
  );
}
