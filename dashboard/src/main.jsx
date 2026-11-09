import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./components/live.css";
import "./components/map.css";
import "./components/Peek.css";
import "./components/settings.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
