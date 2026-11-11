import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fortawesome/fontawesome-svg-core/styles.css";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./components/live.css";
import "./components/map.css";
import "./components/Peek.css";
import "./components/settings.css";
import "./components/overview.css";
import "./components/palette.css";
import App from "./App.jsx";
import { applySavedFont } from "./components/FontPicker.jsx"; // temporary font test
import { applySavedSuspiciousColor } from "./components/SuspiciousColorPicker.jsx"; // temporary Suspicious color test

applySavedFont();
applySavedSuspiciousColor();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
