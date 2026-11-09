import "./styles/app.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Sidebar, { PAGES } from "./components/Sidebar.jsx";
import TopBar from "./components/TopBar.jsx";
import LivePage from "./components/LivePage.jsx";
import DevicesPage from "./components/DevicesPage.jsx";
import SettingsPage from "./components/SettingsPage.jsx";
import Peek from "./components/Peek.jsx";
import { getJson, postJson } from "./lib/api.js";
import { hasGps, sortAlerts } from "./lib/alertMeta.js";
import { effectiveSettings, loadBool, saveBool, useSettings } from "./lib/settings.js";
import { playAlertTone, unlockAudio } from "./lib/sound.js";
import { useEffectiveTheme } from "./lib/theme.js";
import { usePolling } from "./lib/usePolling.js";

const ALERTS_MS = 3000;
const STATUS_MS = 5000;
const DEVICES_MS = 10000;
const URGENT = new Set(["MEDICAL", "SUSPICIOUS"]);

function readPage() {
  const id = window.location.hash.replace(/^#\/?/, "");
  return PAGES.some((p) => p.id === id) ? id : "live";
}

function usePage() {
  const [page, setPage] = useState(readPage);
  useEffect(() => {
    const onHash = () => setPage(readPage());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return page;
}

export default function App() {
  const { settings, update, reset } = useSettings();
  const theme = useEffectiveTheme(settings.theme);
  const page = usePage();

  const [collapsed, setCollapsed] = useState(() => loadBool("safeping.sidebarCollapsed", false));
  const toggleSidebar = useCallback(() => {
    setCollapsed((c) => {
      saveBool("safeping.sidebarCollapsed", !c);
      return !c;
    });
  }, []);

  // ---------- /api/config, once (keeps retrying until it works) ----------
  const [config, setConfig] = useState(null);
  const [configLoaded, setConfigLoaded] = useState(false);
  useEffect(() => {
    let stopped = false;
    let timer;
    const load = () =>
      getJson("/api/config")
        .then((c) => {
          if (stopped) return;
          setConfig(c);
          setConfigLoaded(true);
        })
        .catch(() => {
          if (stopped) return;
          setConfigLoaded(true); // show OpenStreetMap tiles meanwhile
          timer = setTimeout(load, 10000);
        });
    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);

  const eff = useMemo(() => effectiveSettings(settings, config), [settings, config]);
  const effRef = useRef(eff);
  effRef.current = eff;

  // Browsers keep audio locked until a click. If sound was left on, unlock on the first click or key.
  useEffect(() => {
    if (!settings.sound) return undefined;
    const unlock = () => unlockAudio();
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, [settings.sound]);

  // ---------- /api/alerts every 3 s ----------
  const [alerts, setAlerts] = useState(null);
  const [skew, setSkew] = useState(0); // server time minus browser time, in seconds
  const [alertsFailed, setAlertsFailed] = useState(false);
  const [flyTarget, setFlyTarget] = useState(null);
  const seenIds = useRef(null);
  const requestSeq = useRef(0);
  const appliedSeq = useRef(0);

  const noticeNew = useCallback((list) => {
    if (seenIds.current === null) {
      seenIds.current = new Set(list.map((a) => a.id)); // first load: nothing is "new"
      return;
    }
    const fresh = list.filter((a) => !seenIds.current.has(a.id));
    fresh.forEach((a) => seenIds.current.add(a.id));
    const urgent = fresh.filter((a) => !a.acknowledged && URGENT.has(a.alert_type));
    if (!urgent.length) return;
    const s = effRef.current;
    if (s.sound) playAlertTone();
    const target = urgent.filter(hasGps).sort((a, b) => a.priority - b.priority || b.id - a.id)[0];
    if (s.autoZoom && target) {
      setFlyTarget({ id: target.id, latitude: target.latitude, longitude: target.longitude });
    }
  }, []);

  const refreshAlerts = useCallback(async () => {
    const seq = ++requestSeq.current;
    try {
      const status = effRef.current.showStatus ? "1" : "0";
      const data = await getJson("/api/alerts?limit=200&status=" + status);
      if (seq < appliedSeq.current) return; // a newer answer is already on screen
      appliedSeq.current = seq;
      setSkew(data.server_time - Date.now() / 1000);
      setAlertsFailed(false);
      noticeNew(data.alerts);
      setAlerts(data.alerts);
    } catch {
      if (seq >= appliedSeq.current) setAlertsFailed(true);
    }
  }, [noticeNew]);

  usePolling(refreshAlerts, ALERTS_MS, true, [settings.showStatus]);

  // ---------- /api/status every 5 s ----------
  const [status, setStatus] = useState(null);
  const [statusFailed, setStatusFailed] = useState(false);
  usePolling(
    () =>
      getJson("/api/status")
        .then((s) => {
          setStatus(s);
          setStatusFailed(false);
        })
        .catch(() => setStatusFailed(true)),
    STATUS_MS,
  );

  // ---------- /api/devices every 10 s, only on the Devices page ----------
  const [devices, setDevices] = useState(null);
  const [devicesFailed, setDevicesFailed] = useState(false);
  usePolling(
    () =>
      getJson("/api/devices")
        .then((d) => {
          setDevices(d.devices);
          setDevicesFailed(false);
        })
        .catch(() => setDevicesFailed(true)),
    DEVICES_MS,
    page === "devices",
  );

  const unreachable = alertsFailed || statusFailed || (page === "devices" && devicesFailed);

  // ---------- list ----------
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [highlightedId, setHighlightedId] = useState(null);
  const visible = useMemo(() => {
    if (alerts === null) return null;
    return sortAlerts(alerts.filter((a) => typeFilter === "ALL" || a.alert_type === typeFilter));
  }, [alerts, typeFilter]);
  const openCount = alerts ? alerts.filter((a) => !a.acknowledged && a.alert_type !== "STATUS").length : 0;

  useEffect(() => {
    document.title = (openCount ? "(" + openCount + ") " : "") + "SafePing";
  }, [openCount]);

  // ---------- peek ----------
  const [selectedId, setSelectedId] = useState(null);
  const selectedRef = useRef(null);
  const openerRef = useRef(null);
  const cardRefs = useRef(new Map());

  const openPeek = useCallback((id) => {
    openerRef.current = document.activeElement;
    selectedRef.current = id;
    setSelectedId(id);
  }, []);

  const closePeek = useCallback(() => {
    const id = selectedRef.current;
    selectedRef.current = null;
    setSelectedId(null);
    // Give focus back to the alert's card. If it is gone (resolved), use the first card.
    requestAnimationFrame(() => {
      const card = cardRefs.current.get(id);
      const opener = openerRef.current;
      const target =
        card || (opener && document.contains(opener) ? opener : cardRefs.current.values().next().value);
      if (target && target.focus) target.focus();
    });
  }, []);

  const selectedAlert = alerts && selectedId !== null ? alerts.find((a) => a.id === selectedId) : null;

  // The alert left the list (resolved, or STATUS hidden): close the peek.
  useEffect(() => {
    if (selectedId !== null && alerts && !alerts.some((a) => a.id === selectedId)) closePeek();
  }, [alerts, selectedId, closePeek]);

  const acknowledge = useCallback(
    async (id) => {
      await postJson("/api/ack", { id });
      await refreshAlerts();
    },
    [refreshAlerts],
  );

  const resolve = useCallback(
    async (id) => {
      await postJson("/api/resolve", { id });
      await refreshAlerts();
    },
    [refreshAlerts],
  );

  const nowServer = Date.now() / 1000 + skew;
  const title = PAGES.find((p) => p.id === page).label;

  return (
    <>
      <div className={"app" + (collapsed ? " app--collapsed" : "")} inert={selectedAlert ? true : undefined}>
        <Sidebar page={page} collapsed={collapsed} onToggle={toggleSidebar} />
        <div className="main">
          <TopBar
            title={title}
            status={status}
            unreachable={unreachable}
            skew={skew}
            timeFormat={settings.timeFormat}
            refMaxAge={(config && config.ref_max_age_s) || 120}
          />
          <main className={"content content--" + page}>
            {page === "live" && (
              <LivePage
                alerts={visible}
                openCount={openCount}
                loadFailed={alertsFailed}
                typeFilter={typeFilter}
                setTypeFilter={setTypeFilter}
                settings={eff}
                update={update}
                theme={theme}
                config={config}
                configLoaded={configLoaded}
                nowServer={nowServer}
                highlightedId={highlightedId}
                setHighlightedId={setHighlightedId}
                onOpen={openPeek}
                flyTarget={flyTarget}
                cardRefs={cardRefs}
              />
            )}
            {page === "devices" && (
              <DevicesPage
                devices={devices}
                loadFailed={devicesFailed}
                nowServer={nowServer}
                timeFormat={settings.timeFormat}
              />
            )}
            {page === "settings" && (
              <SettingsPage
                settings={settings}
                effective={eff}
                update={update}
                reset={reset}
                hasCartoKey={!!(config && config.carto_key)}
              />
            )}
          </main>
        </div>
      </div>
      {selectedAlert && page === "live" && (
        <Peek
          alert={selectedAlert}
          settings={eff}
          theme={theme}
          cartoKey={config && config.carto_key}
          nowServer={nowServer}
          onClose={closePeek}
          onAck={acknowledge}
          onResolve={resolve}
        />
      )}
    </>
  );
}
