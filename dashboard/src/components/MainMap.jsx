import { useEffect, useRef } from "react";
import { MapContainer, useMap } from "react-leaflet";
import { hasGps } from "../lib/alertMeta.js";
import { useReducedMotion } from "../lib/theme.js";
import { AlertMarker, AlertZones, AttributionPrefix, BaseTiles, DEFAULT_CENTER, SizeWatcher } from "./mapParts.jsx";

/** Fits all open alerts once, on first load. Then flies to new urgent alerts if auto-zoom is on. */
function MapController({ alerts, flyTarget, reducedMotion }) {
  const map = useMap();
  const fitted = useRef(false);

  useEffect(() => {
    if (fitted.current || alerts === null) return;
    const points = alerts.filter((a) => !a.acknowledged && hasGps(a)).map((a) => [a.latitude, a.longitude]);
    fitted.current = true;
    if (points.length) map.fitBounds(points, { maxZoom: 18, padding: [48, 48], animate: false });
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

export default function MainMap({ alerts, theme, settings, cartoKey, configLoaded, highlightedId, onOpen, onHover, flyTarget }) {
  const reducedMotion = useReducedMotion();
  const withGps = (alerts || []).filter(hasGps);
  // Acknowledged first so open alerts draw on top.
  const ordered = withGps.slice().sort((a, b) => Number(b.acknowledged) - Number(a.acknowledged));

  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={16}
      className="main-map"
      zoomAnimation={!reducedMotion}
      fadeAnimation={!reducedMotion}
      markerZoomAnimation={!reducedMotion}
    >
      {configLoaded && <BaseTiles theme={theme} labels={settings.mapLabels} cartoKey={cartoKey} />}
      <AttributionPrefix />
      <SizeWatcher />
      <MapController alerts={alerts} flyTarget={flyTarget} reducedMotion={reducedMotion} />
      {ordered.map((a) => (
        <AlertZones key={"z" + a.id} alert={a} sightRadius={settings.sightRadius} />
      ))}
      {ordered.map((a) => (
        <AlertMarker
          key={"m" + a.id}
          alert={a}
          highlighted={a.id === highlightedId}
          onOpen={onOpen}
          onHover={onHover}
        />
      ))}
    </MapContainer>
  );
}
