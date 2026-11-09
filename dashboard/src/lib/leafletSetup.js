// leaflet.markercluster is an old script that looks for a global "L".
// Import this file before it, so the global exists.
import L from "leaflet";

window.L = L;

export default L;
