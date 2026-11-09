import "./styles/app.css";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Sidebar, { PAGES } from "./components/Sidebar.jsx";
import TopBar from "./components/TopBar.jsx";
import LivePage, { VIEWS } from "./components/LivePage.jsx";
import DevicesPage from "./components/DevicesPage.jsx";

// Overview carries the chart library, so it loads only when opened. Live stays light.
const OverviewPage = lazy(() => import("./components/OverviewPage.jsx"));
import AlertPeek from "./components/AlertPeek.jsx";
import DevicePeek from "./components/DevicePeek.jsx";
import SettingsModal from "./components/SettingsModal.jsx";
import { getJson, postJson } from "./lib/api.js";
import { alertState, hasGps, isOpenMedical, sortAlerts } from "./lib/alertMeta.js";
import { effectiveSettings, loadBool, loadChoice, saveBool, saveChoice, useSettings } from "./lib/settings.js";
import { playAlertTone, unlockAudio } from "./lib/sound.js";
import { useEffectiveTheme } from "./lib/theme.js";
import { usePolling } from "./lib/usePolling.js";

const ALERTS_MS = 3000;
const STATUS_MS = 5000;
const DEVICES_MS = 10000;
const URGENT = new Set(["MEDICAL", "SUSPICIOUS"]);
const STATE_FILTERS = { action: "open", acknowledged: "acknowledged" };

function readHash() {
  return window.location.hash.replace(/^#\/?/, "");
}

const PAGE_IDS = PAGES.map((p) => p.id);

/** The page in the address (#/live), or else the last page used. Live the first time. */
function usePage() {
  const read = () => (PAGE_IDS.includes(readHash()) ? readHash() : loadChoice("safeping.page", PAGE_IDS, "live"));
  const [page, setPage] = useState(read);
  useEffect(() => {
    const onHash = () => setPage(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => saveChoice("safeping.page", page), [page]);
  return page;
}

/** Remembers which element to focus for each id (a row, a panel row). */
function useFocusRegistry() {
  const map = useRef(new Map());
  const register = useCallback((id, node) => {
    if (node) map.current.set(id, node);
    else if (map.current.get(id) && !map.current.get(id).isConnected) map.current.delete(id);
  }, []);
  const focus = useCallback((id) => {
    const node = map.current.get(id);
    if (node && node.isConnected) {
      node.focus();
      return true;
    }
    return false;
  }, []);
  return [register, focus];
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

  const [view, setViewState] = useState(() => loadChoice("safeping.liveView", VIEWS.map((v) => v.id), "split"));
  const setView = useCallback((v) => {
    saveChoice("safeping.liveView", v);
    setViewState(v);
  }, []);
  const [panelCollapsed, setPanelCollapsed] = useState(() => loadBool("safeping.mapPanelCollapsed", false));
  const togglePanel = useCallback(() => {
    setPanelCollapsed((c) => {
      saveBool("safeping.mapPanelCollapsed", !c);
      return !c;
    });
  }, []);

  // ---------- /api/config, once (retries until it works) ----------
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
          setConfigLoaded(true); // OpenStreetMap tiles meanwhile
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

  // ---------- filters ----------
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [stateFilter, setStateFilter] = useState("action");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const searchInputRef = useRef(null);
  const stateRef = useRef(stateFilter);
  stateRef.current = stateFilter;

  // ---------- /api/alerts every 3 s ----------
  const [alerts, setAlerts] = useState(null);
  const [skew, setSkew] = useState(0);
  const [alertsFailed, setAlertsFailed] = useState(false);
  const [flyTarget, setFlyTarget] = useState(null);
  const seenIds = useRef(null);
  const requestSeq = useRef(0);
  const appliedSeq = useRef(0);

  const noticeNew = useCallback((list) => {
    if (seenIds.current === null) {
      seenIds.current = new Set(list.map((a) => a.id)); // first load: nothing is new
      return;
    }
    const fresh = list.filter((a) => !seenIds.current.has(a.id));
    fresh.forEach((a) => seenIds.current.add(a.id));
    const urgent = fresh.filter((a) => alertState(a) === "open" && URGENT.has(a.alert_type));
    if (!urgent.length) return;
    const s = effRef.current;
    if (s.sound) playAlertTone();
    const target = urgent.filter(hasGps).sort((a, b) => a.priority - b.priority || b.id - a.id)[0];
    if (s.autoZoom && target) setFlyTarget({ id: target.id, latitude: target.latitude, longitude: target.longitude });
  }, []);

  const refreshAlerts = useCallback(async () => {
    const seq = ++requestSeq.current;
    try {
      const all = stateRef.current === "all";
      const url = "/api/alerts?limit=" + (all ? 500 : 200) + "&status=" + (effRef.current.showStatus ? "1" : "0") + (all ? "&resolved=1" : "");
      const data = await getJson(url);
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

  usePolling(refreshAlerts, ALERTS_MS, true, [settings.showStatus, stateFilter === "all"]);

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

  // ---------- modals ----------
  const [selectedId, setSelectedId] = useState(null);
  const [deviceId, setDeviceId] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(() => readHash() === "settings");
  const settingsOpener = useRef(null);
  const [registerAlertFocus, focusAlert] = useFocusRegistry();
  const [registerDeviceFocus, focusDevice] = useFocusRegistry();

  // ---------- /api/devices every 10 s: Devices page, device peek or Settings ----------
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
    page === "devices" || settingsOpen,
  );

  // ---------- one device's history while its peek is open ----------
  const [history, setHistory] = useState(null);
  const [historyFailed, setHistoryFailed] = useState(false);
  useEffect(() => setHistory(null), [deviceId]);
  usePolling(
    () =>
      getJson("/api/devices/" + encodeURIComponent(deviceId) + "/alerts")
        .then((d) => {
          setHistory(d.alerts);
          setHistoryFailed(false);
        })
        .catch(() => setHistoryFailed(true)),
    DEVICES_MS,
    deviceId !== null,
    [deviceId],
  );

  const unreachable = alertsFailed || statusFailed || (page === "devices" && devicesFailed);

  // ---------- what the list and map show ----------
  const [highlightedId, setHighlightedId] = useState(null);
  const visible = useMemo(() => {
    if (alerts === null) return null;
    const q = query.trim().toLowerCase();
    return sortAlerts(
      alerts.filter(
        (a) =>
          (typeFilter === "ALL" || a.alert_type === typeFilter) &&
          (stateFilter === "all" || alertState(a) === STATE_FILTERS[stateFilter]) &&
          (!q || (a.student_name || "").toLowerCase().includes(q) || a.device_id.toLowerCase().includes(q)),
      ),
    );
  }, [alerts, typeFilter, stateFilter, query]);

  const openAlerts = alerts ? alerts.filter((a) => alertState(a) === "open" && a.alert_type !== "STATUS") : [];
  const openCount = openAlerts.length;
  const hasOpenMedical = openAlerts.some(isOpenMedical);

  useEffect(() => {
    document.title = (openCount ? "(" + openCount + ") " : "") + "SafePing";
  }, [openCount]);

  const openPeek = useCallback((id) => setSelectedId(id), []);
  const closePeek = useCallback(() => setSelectedId(null), []);
  const selectedAlert = alerts && selectedId !== null ? alerts.find((a) => a.id === selectedId) : null;

  // The alert left the data (resolved in a view without resolved alerts): close the peek.
  useEffect(() => {
    if (selectedId !== null && alerts && !alerts.some((a) => a.id === selectedId)) setSelectedId(null);
  }, [alerts, selectedId]);

  const selectedDevice = devices && deviceId !== null ? devices.find((d) => d.device_id === deviceId) : null;

  const openSettings = useCallback((from) => {
    settingsOpener.current = from || null;
    setSettingsOpen(true);
  }, []);

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

  // ---------- keyboard: Ctrl+\ sidebar, Ctrl+K search ----------
  const openSearch = useCallback(() => {
    if (page !== "live") window.location.hash = "#/live";
    setSearchOpen(true);
    setTimeout(() => searchInputRef.current && searchInputRef.current.focus(), 0);
  }, [page]);

  useEffect(() => {
    function onKey(event) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const modalOpen = selectedId !== null || deviceId !== null || settingsOpen;
      if (event.key === "\\") {
        event.preventDefault();
        if (!modalOpen) toggleSidebar();
      } else if (event.key === "k" || event.key === "K") {
        event.preventDefault();
        if (!modalOpen) openSearch();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleSidebar, openSearch, selectedId, deviceId, settingsOpen]);

  const nowServer = Date.now() / 1000 + skew;
  const modalOpen = !!selectedAlert || !!selectedDevice || settingsOpen;

  return (
    <>
      <div className={"app" + (collapsed ? " is-collapsed" : "")} inert={modalOpen ? true : undefined}>
        <Sidebar
          page={page}
          collapsed={collapsed}
          onToggle={toggleSidebar}
          openCount={openCount}
          hasOpenMedical={hasOpenMedical}
          serverOk={!alertsFailed && !statusFailed}
          onSearch={openSearch}
          onOpenSettings={openSettings}
        />
        <div className="main">
          <TopBar
            crumb={PAGES.find((p) => p.id === page).label}
            status={status}
            unreachable={unreachable}
            skew={skew}
            timeFormat={settings.timeFormat}
            refMaxAge={(config && config.ref_max_age_s) || 120}
          />
          <main className="content">
            {page === "overview" && (
              <Suspense fallback={null}>
                <OverviewPage timeFormat={settings.timeFormat} />
              </Suspense>
            )}
            {page === "live" && (
              <LivePage
                alerts={visible}
                loadFailed={alertsFailed}
                view={view}
                setView={setView}
                typeFilter={typeFilter}
                setTypeFilter={setTypeFilter}
                stateFilter={stateFilter}
                setStateFilter={setStateFilter}
                query={query}
                setQuery={setQuery}
                searchOpen={searchOpen}
                setSearchOpen={setSearchOpen}
                searchInputRef={searchInputRef}
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
                panelCollapsed={panelCollapsed}
                togglePanel={togglePanel}
                registerFocus={registerAlertFocus}
              />
            )}
            {page === "devices" && (
              <DevicesPage
                devices={devices}
                loadFailed={devicesFailed}
                nowServer={nowServer}
                timeFormat={settings.timeFormat}
                onOpen={setDeviceId}
                registerFocus={registerDeviceFocus}
              />
            )}
          </main>
        </div>
      </div>

      {selectedAlert && (
        <AlertPeek
          key={selectedAlert.id}
          alert={selectedAlert}
          settings={eff}
          update={update}
          theme={theme}
          cartoKey={config && config.carto_key}
          nowServer={nowServer}
          onClose={closePeek}
          onAck={acknowledge}
          onResolve={resolve}
          returnFocus={() => focusAlert(selectedAlert.id)}
        />
      )}
      {selectedDevice && (
        <DevicePeek
          key={selectedDevice.device_id}
          device={selectedDevice}
          history={history}
          historyFailed={historyFailed}
          nowServer={nowServer}
          timeFormat={settings.timeFormat}
          onClose={() => setDeviceId(null)}
          returnFocus={() => focusDevice(selectedDevice.device_id)}
        />
      )}
      {settingsOpen && (
        <SettingsModal
          settings={settings}
          effective={eff}
          update={update}
          reset={reset}
          config={config}
          devices={devices}
          onClose={() => {
            setSettingsOpen(false);
            if (readHash() === "settings") window.location.hash = "#/" + page;
          }}
          returnFocus={() => {
            const el = settingsOpener.current;
            if (el && el.isConnected) {
              el.focus();
              return true;
            }
            return false;
          }}
        />
      )}
    </>
  );
}
