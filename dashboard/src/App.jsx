import "./styles/app.css";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Sidebar, { PAGES } from "./components/Sidebar.jsx";
import TopBar, { PreviewBanner } from "./components/TopBar.jsx";
import { isEmptyPreview, stopEmptyPreview } from "./lib/preview.js";
import LivePage, { VIEWS } from "./components/LivePage.jsx";
import DevicesPage from "./components/DevicesPage.jsx";

// Overview carries the chart library, so it loads only when opened. Live stays light.
const OverviewPage = lazy(() => import("./components/OverviewPage.jsx"));
import AlertPeek from "./components/AlertPeek.jsx";
import DevicePeek from "./components/DevicePeek.jsx";
import SearchPalette from "./components/SearchPalette.jsx";
import SettingsModal from "./components/SettingsModal.jsx";
import { getJson, postJson } from "./lib/api.js";
import { alertState, hasGps, isUrgentOpen, SORT_ORDERS, sortAlerts, URGENT_TYPES } from "./lib/alertMeta.js";
import { useNow } from "./lib/clock.js";
import { effectiveSettings, loadBool, loadChoice, saveBool, saveChoice, useSettings } from "./lib/settings.js";
import { playAlertTone, unlockAudio } from "./lib/sound.js";
import { useEffectiveTheme } from "./lib/theme.js";
import { usePolling } from "./lib/usePolling.js";

const ALERTS_MS = 3000;
const STATUS_MS = 5000;
const DEVICES_MS = 10000;
const PEEK_MS = 5000;
const SOUND_TYPES = new Set(["MEDICAL", "SUSPICIOUS"]); // new alerts that play the tone and auto-zoom
const STATE_FILTERS = { action: "open", acknowledged: "acknowledged" };
const NARROW = "(max-width: 1279px)"; // the sidebar folds to icons below this width
const EMPTY_PREVIEW = isEmptyPreview(); // Settings > About > Show an empty dashboard

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

function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => !!(window.matchMedia && window.matchMedia(query).matches));
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return matches;
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

function focusIfThere(el) {
  if (el && el.isConnected) {
    el.focus();
    return true;
  }
  return false;
}

export default function App() {
  const { settings, update, reset } = useSettings();
  const theme = useEffectiveTheme(settings.theme);
  const page = usePage();

  // ---------- sidebar: the saved choice, but folded to icons under 1280 px unless opened ----------
  const narrow = useMediaQuery(NARROW);
  const [collapsedPref, setCollapsedPref] = useState(() => loadBool("safeping.sidebarCollapsed", false));
  const [narrowOpen, setNarrowOpen] = useState(false);
  useEffect(() => {
    if (!narrow) setNarrowOpen(false);
  }, [narrow]);
  const collapsed = narrow ? !narrowOpen : collapsedPref;
  const toggleSidebar = useCallback(() => {
    if (narrow) {
      setNarrowOpen((o) => !o);
      return;
    }
    setCollapsedPref((c) => {
      saveBool("safeping.sidebarCollapsed", !c);
      return !c;
    });
  }, [narrow]);

  const [view, setViewState] = useState(() => loadChoice("safeping.liveView", VIEWS.map((v) => v.id), "split"));
  const setView = useCallback((v) => {
    saveChoice("safeping.liveView", v);
    setViewState(v);
  }, []);
  // Split view: how much of the width the list takes, in percent. Saved when a drag ends.
  const [split, setSplit] = useState(() => {
    let n = 50;
    try {
      n = Number(localStorage.getItem("safeping.splitPct") || 50);
    } catch {
      // storage blocked: start in the middle
    }
    return Number.isFinite(n) && n >= 10 && n <= 90 ? n : 50;
  });
  const saveSplit = useCallback((pct) => saveChoice("safeping.splitPct", String(pct)), []);
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

  // ---------- Live filters ----------
  const [typeFilter, setTypeFilter] = useState("ALL"); // a type, "URGENT" (Medical and Silent) or "ALL"
  const [stateFilter, setStateFilter] = useState("action");
  const [query, setQuery] = useState("");
  const [sortOrder, setSortOrderState] = useState(() => loadChoice("safeping.liveSort", SORT_ORDERS.map((o) => o.value), "newest"));
  const setSortOrder = useCallback((v) => {
    saveChoice("safeping.liveSort", v);
    setSortOrderState(v);
  }, []);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchInputRef = useRef(null);
  const stateRef = useRef(stateFilter);
  stateRef.current = stateFilter;

  // ---------- /api/alerts every 3 s ----------
  const [alerts, setAlerts] = useState(null);
  const alertsRef = useRef(null);
  alertsRef.current = alerts;
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
    const urgent = fresh.filter((a) => alertState(a) === "open" && SOUND_TYPES.has(a.alert_type));
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
  // peek: the open Alert Peek. live: opened from the Live list (it closes when the alert
  // leaves that list, as before). Otherwise it was opened from Overview or search, and
  // the alert is loaded from /api/alerts/<id> when it is not in the Live list.
  const [peek, setPeek] = useState(null); // { id, live, from }
  const [remoteAlert, setRemoteAlert] = useState(null);
  const [deviceOpen, setDeviceOpen] = useState(null); // { id, from }
  const [settingsOpen, setSettingsOpen] = useState(() => readHash() === "settings");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const settingsOpener = useRef(null);
  const paletteOpener = useRef(null);
  const [registerAlertFocus, focusAlert] = useFocusRegistry();
  const [registerDeviceFocus, focusDevice] = useFocusRegistry();
  const deviceId = deviceOpen ? deviceOpen.id : null;

  // ---------- /api/devices every 10 s: Devices page, a device peek or Settings ----------
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
    page === "devices" || settingsOpen || deviceId !== null,
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

  // ---------- one device's boot reports (self-checks) while its peek is open ----------
  const [boots, setBoots] = useState(null);
  const [bootsFailed, setBootsFailed] = useState(false);
  useEffect(() => setBoots(null), [deviceId]);
  usePolling(
    () =>
      getJson("/api/devices/" + encodeURIComponent(deviceId) + "/boots")
        .then((d) => {
          setBoots(d.boots);
          setBootsFailed(false);
        })
        .catch(() => setBootsFailed(true)),
    DEVICES_MS,
    deviceId !== null,
    [deviceId],
  );

  // ---------- an older alert, while its peek is open ----------
  const peekId = peek ? peek.id : null;
  const remote = peek !== null && !peek.live;
  const remoteRef = useRef(null);
  remoteRef.current = remoteAlert;
  const loadRemote = useCallback(() => {
    if (peekId === null) return Promise.resolve();
    return getJson("/api/alerts/" + peekId)
      .then((d) => setRemoteAlert(d.alert))
      .catch((error) => {
        // No such alert, or it never loaded and Live does not have it either: nothing to show.
        const loaded = remoteRef.current && remoteRef.current.id === peekId;
        const inLive = alertsRef.current && alertsRef.current.some((a) => a.id === peekId);
        if (String(error.message).includes("404") || (!loaded && !inLive)) setPeek(null);
      });
  }, [peekId]);
  useEffect(() => setRemoteAlert(null), [peekId]);
  usePolling(loadRemote, PEEK_MS, remote, [peekId]);

  const unreachable = alertsFailed || statusFailed || (page === "devices" && devicesFailed);

  // ---------- what the list and map show ----------
  // hover.from: "row" (a table or panel row) or "map" (a marker). A marker hover selects its row.
  const [hover, setHover] = useState({ id: null, from: null });
  const setRowHover = useCallback((id) => setHover({ id, from: id === null ? null : "row" }), []);
  const setMarkerHover = useCallback((id) => setHover({ id, from: id === null ? null : "map" }), []);
  const visible = useMemo(() => {
    if (alerts === null) return null;
    const q = query.trim().toLowerCase();
    return sortAlerts(
      alerts.filter(
        (a) =>
          (typeFilter === "ALL" || a.alert_type === typeFilter || (typeFilter === "URGENT" && URGENT_TYPES.includes(a.alert_type))) &&
          (stateFilter === "all" || alertState(a) === STATE_FILTERS[stateFilter]) &&
          (!q || (a.student_name || "").toLowerCase().includes(q) || a.device_id.toLowerCase().includes(q)),
      ),
      sortOrder,
    );
  }, [alerts, typeFilter, stateFilter, query, sortOrder]);

  // The newest alert id in the poll. Overview reloads its numbers when it changes.
  const latestAlertId = alerts && alerts.length ? Math.max(...alerts.map((a) => a.id)) : null;

  const openAlerts = alerts ? alerts.filter((a) => alertState(a) === "open" && a.alert_type !== "STATUS") : [];
  const openCount = openAlerts.length;
  const hasUrgentOpen = openAlerts.some(isUrgentOpen);

  useEffect(() => {
    document.title = (EMPTY_PREVIEW ? "(Preview) " : "") + (openCount ? "(" + openCount + ") " : "") + "SafePing";
  }, [openCount]);

  /** Opens the Alert Peek. from names the place it was opened from, for the breadcrumb. */
  const openAlert = useCallback((id, from) => {
    const live = !from && !!alertsRef.current && alertsRef.current.some((a) => a.id === id);
    setPeek({ id, live, from: from || null });
  }, []);
  const openLivePeek = useCallback((id) => openAlert(id), [openAlert]);
  const closePeek = useCallback(() => setPeek(null), []);

  const liveAlert = alerts && peek ? alerts.find((a) => a.id === peek.id) : null;
  const selectedAlert = liveAlert || (remoteAlert && peek && remoteAlert.id === peek.id ? remoteAlert : null);

  // An alert opened from Live left the list (resolved in a view without resolved alerts): close the peek.
  useEffect(() => {
    if (peek && peek.live && alerts && !alerts.some((a) => a.id === peek.id)) setPeek(null);
  }, [alerts, peek]);

  const openDevice = useCallback((id, from) => setDeviceOpen({ id, from: from || null }), []);
  const selectedDevice = devices && deviceId !== null ? devices.find((d) => d.device_id === deviceId) : null;

  const openSettings = useCallback((from) => {
    settingsOpener.current = from || null;
    setSettingsOpen(true);
  }, []);

  const acknowledge = useCallback(
    async (id) => {
      await postJson("/api/ack", { id });
      await refreshAlerts();
      if (remote) await loadRemote();
    },
    [refreshAlerts, remote, loadRemote],
  );
  const resolve = useCallback(
    async (id) => {
      await postJson("/api/resolve", { id });
      await refreshAlerts();
      if (remote) await loadRemote();
    },
    [refreshAlerts, remote, loadRemote],
  );

  /** Overview tiles: go to Live with these filters. */
  const goLive = useCallback(({ state = "action", type = "ALL" } = {}) => {
    setStateFilter(state);
    setTypeFilter(type);
    setQuery("");
    setSearchOpen(false);
    window.location.hash = "#/live";
  }, []);

  // ---------- Find a student (Ctrl+K) ----------
  const openPalette = useCallback((from) => {
    paletteOpener.current = from || document.activeElement;
    setPaletteOpen(true);
  }, []);
  const closePalette = useCallback(() => {
    setPaletteOpen(false);
    requestAnimationFrame(() => focusIfThere(paletteOpener.current));
  }, []);

  const modalOpen = !!selectedAlert || !!selectedDevice || settingsOpen;

  useEffect(() => {
    function onKey(event) {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      if (event.key === "\\") {
        event.preventDefault();
        if (!modalOpen && !paletteOpen) toggleSidebar();
      } else if (event.key === "k" || event.key === "K") {
        event.preventDefault();
        if (!modalOpen && !paletteOpen) openPalette();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleSidebar, openPalette, modalOpen, paletteOpen]);

  const nowServer = useNow(skew); // one shared 5 s timer for every relative time
  const pageLabel = PAGES.find((p) => p.id === page).label;
  const peekFrom = peek && peek.from ? peek.from : pageLabel;
  const selectedRowId = (hover.from === "map" ? hover.id : null) ?? (peek ? peek.id : null);

  return (
    <>
      <div className={"app" + (collapsed ? " is-collapsed" : "")} inert={modalOpen || paletteOpen ? true : undefined}>
        <Sidebar
          page={page}
          collapsed={collapsed}
          onToggle={toggleSidebar}
          openCount={openCount}
          hasUrgentOpen={hasUrgentOpen}
          serverOk={!alertsFailed && !statusFailed}
          onFind={openPalette}
          onOpenSettings={openSettings}
        />
        <div className="main">
          {EMPTY_PREVIEW && <PreviewBanner onExit={stopEmptyPreview} />}
          <TopBar
            crumb={pageLabel}
            status={status}
            unreachable={unreachable}
            skew={skew}
            timeFormat={settings.timeFormat}
            refMaxAge={(config && config.ref_max_age_s) || 120}
          />
          <main className="content">
            {page === "overview" && (
              <Suspense fallback={null}>
                <OverviewPage
                  timeFormat={settings.timeFormat}
                  nowServer={nowServer}
                  latestAlertId={latestAlertId}
                  theme={theme}
                  settings={eff}
                  cartoKey={config && config.carto_key}
                  configLoaded={configLoaded}
                  onOpenAlert={(id) => openAlert(id, "Overview")}
                  goLive={goLive}
                />
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
                sortOrder={sortOrder}
                setSortOrder={setSortOrder}
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
                highlightedId={hover.id}
                selectedRowId={selectedRowId}
                selectedId={peek ? peek.id : null}
                onRowHover={setRowHover}
                onMarkerHover={setMarkerHover}
                onOpen={openLivePeek}
                onAck={acknowledge}
                flyTarget={flyTarget}
                panelCollapsed={panelCollapsed}
                togglePanel={togglePanel}
                registerFocus={registerAlertFocus}
                split={split}
                setSplit={setSplit}
                saveSplit={saveSplit}
              />
            )}
            {page === "devices" && (
              <DevicesPage
                devices={devices}
                loadFailed={devicesFailed}
                nowServer={nowServer}
                timeFormat={settings.timeFormat}
                onOpen={openDevice}
                selectedId={deviceId}
                registerFocus={registerDeviceFocus}
              />
            )}
          </main>
        </div>
      </div>

      {paletteOpen && (
        <SearchPalette
          onClose={closePalette}
          onOpenAlert={(id) => {
            setPaletteOpen(false);
            openAlert(id, "Search");
          }}
          onOpenDevice={(id) => {
            setPaletteOpen(false);
            openDevice(id, "Search");
          }}
          showStatus={settings.showStatus}
          nowServer={nowServer}
          timeFormat={settings.timeFormat}
        />
      )}
      {selectedAlert && (
        <AlertPeek
          key={selectedAlert.id}
          alert={selectedAlert}
          crumb={peekFrom}
          settings={eff}
          update={update}
          theme={theme}
          cartoKey={config && config.carto_key}
          nowServer={nowServer}
          onClose={closePeek}
          onAck={acknowledge}
          onResolve={resolve}
          returnFocus={() => (peek && peek.from === "Search" ? focusIfThere(paletteOpener.current) : focusAlert(selectedAlert.id))}
        />
      )}
      {selectedDevice && (
        <DevicePeek
          key={selectedDevice.device_id}
          device={selectedDevice}
          crumb={deviceOpen && deviceOpen.from ? deviceOpen.from : "Devices"}
          history={history}
          historyFailed={historyFailed}
          boots={boots}
          bootsFailed={bootsFailed}
          nowServer={nowServer}
          timeFormat={settings.timeFormat}
          onClose={() => setDeviceOpen(null)}
          returnFocus={() =>
            deviceOpen && deviceOpen.from === "Search" ? focusIfThere(paletteOpener.current) : focusDevice(selectedDevice.device_id)
          }
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
          refMaxAge={(config && config.ref_max_age_s) || 120}
          onClose={() => {
            setSettingsOpen(false);
            if (readHash() === "settings") window.location.hash = "#/" + page;
          }}
          returnFocus={() => focusIfThere(settingsOpener.current)}
        />
      )}
    </>
  );
}
