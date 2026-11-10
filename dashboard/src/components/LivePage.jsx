import { useRef, useState } from "react";
import AlertMap from "./AlertMap.jsx";
import AlertTable from "./AlertTable.jsx";
import { Segmented } from "./Controls.jsx";
import Icon from "./Icon.jsx";
import Popover from "./Popover.jsx";
import Tooltip from "./Tooltip.jsx";
import { TYPE_ORDER, typeMeta } from "../lib/alertMeta.js";
import { icons } from "../lib/icons.js";
import { TypeIcon } from "./Tags.jsx";

export const VIEWS = [
  { id: "split", label: "Split", icon: icons.split },
  { id: "list", label: "List", icon: icons.list },
  { id: "map", label: "Map", icon: icons.map },
];

const STATE_OPTIONS = [
  { value: "action", label: "Needs action" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "all", label: "All" },
];

function ViewTabs({ view, setView }) {
  function onKeyDown(event) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const i = VIEWS.findIndex((v) => v.id === view);
    const next = VIEWS[(i + (event.key === "ArrowRight" ? 1 : VIEWS.length - 1)) % VIEWS.length];
    setView(next.id);
    event.currentTarget.querySelector('[data-view="' + next.id + '"]').focus();
  }
  return (
    <div className="view-tabs" role="tablist" aria-label="Live view" onKeyDown={onKeyDown}>
      {VIEWS.map(({ id, label, icon }) => (
        <button
          key={id}
          type="button"
          role="tab"
          id={"tab-" + id}
          data-view={id}
          aria-selected={view === id}
          aria-controls="live-panel"
          tabIndex={view === id ? 0 : -1}
          className="view-tab"
          onClick={() => setView(id)}
        >
          <Icon icon={icon} />
          {label}
        </button>
      ))}
    </div>
  );
}

function FilterMenu({ typeFilter, setTypeFilter }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const active = typeFilter !== "ALL";
  const label = !active ? "Filter by type" : typeFilter === "URGENT" ? "Filter: Medical and Silent" : "Filter: " + typeMeta(typeFilter).label;
  const options = [
    { value: "ALL", label: "All types" },
    { value: "URGENT", label: "Medical and Silent" },
    ...TYPE_ORDER.map((t) => ({ value: t, label: typeMeta(t).label, type: t })),
  ];
  return (
    <>
      <Tooltip label={label}>
        <button
          ref={ref}
          type="button"
          className={"icon-btn" + (active ? " is-active" : "")}
          aria-label={label}
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          <Icon icon={icons.filter} />
        </button>
      </Tooltip>
      <Popover anchor={ref.current} open={open} onClose={() => setOpen(false)} label="Filter by type" placement="bottom-end">
        <div className="popover-title">Type</div>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="menuitemradio"
            aria-checked={typeFilter === o.value}
            className="menu-item"
            onClick={() => {
              setTypeFilter(o.value);
              setOpen(false);
            }}
          >
            {o.type ? <TypeIcon type={o.type} size={16} /> : <span className="menu-icon-space" aria-hidden="true" />}
            {o.label}
            {typeFilter === o.value && <Icon icon={icons.acknowledged} className="menu-check" />}
          </button>
        ))}
      </Popover>
    </>
  );
}

function SearchBox({ query, setQuery, searchOpen, setSearchOpen, inputRef }) {
  if (!searchOpen && !query) {
    return (
      <Tooltip label="Filter by student or Fob ID">
        <button type="button" className="icon-btn" aria-label="Filter alerts by student or Fob ID" onClick={() => setSearchOpen(true)}>
          <Icon icon={icons.search} />
        </button>
      </Tooltip>
    );
  }
  return (
    <span className="input-icon search-box">
      <Icon icon={icons.search} size={14} />
      <input
        ref={inputRef}
        type="search"
        className="input"
        placeholder="Student or Fob ID"
        aria-label="Filter alerts by student name or Fob ID"
        value={query}
        autoFocus
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            e.stopPropagation();
            setQuery("");
            setSearchOpen(false);
          }
        }}
        onBlur={() => !query && setSearchOpen(false)}
      />
      {query && (
        <Tooltip label="Clear search">
          <button
            type="button"
            className="icon-btn icon-btn-sm search-clear"
            aria-label="Clear search"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              setQuery("");
              inputRef.current && inputRef.current.focus();
            }}
          >
            <Icon icon={icons.close} />
          </button>
        </Tooltip>
      )}
    </span>
  );
}

const SPLIT_MIN_LIST = 360; // px
const SPLIT_MIN_MAP = 320; // px
const SPLIT_STEP = 2; // percent per arrow key

/** The divider between the list and the map in Split view. Drag it, or focus it and use
    Left and Right. Double-click puts it back in the middle. */
function Splitter({ bodyRef, split, setSplit, saveSplit }) {
  function bounds() {
    const body = bodyRef.current;
    const pad = parseFloat(getComputedStyle(body).paddingLeft) || 0;
    const rect = body.getBoundingClientRect();
    const width = rect.width - pad;
    return { left: rect.left + pad, width, min: (SPLIT_MIN_LIST / width) * 100, max: ((width - SPLIT_MIN_MAP - 8) / width) * 100 };
  }
  const clamp = (pct, b) => Math.round(Math.min(b.max, Math.max(b.min, pct)) * 10) / 10;

  function onPointerDown(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    const handle = event.currentTarget;
    const body = bodyRef.current;
    handle.setPointerCapture(event.pointerId);
    body.classList.add("is-resizing");
    let last = split;
    const move = (e) => {
      const b = bounds();
      last = clamp(((e.clientX - b.left) / b.width) * 100, b);
      setSplit(last);
    };
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
      body.classList.remove("is-resizing");
      saveSplit(last);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  }

  function onKeyDown(event) {
    const b = bounds();
    let next = null;
    if (event.key === "ArrowLeft") next = split - SPLIT_STEP;
    else if (event.key === "ArrowRight") next = split + SPLIT_STEP;
    else if (event.key === "Home") next = b.min;
    else if (event.key === "End") next = b.max;
    else if (event.key === "Enter") next = 50;
    if (next === null) return;
    event.preventDefault();
    const value = clamp(next, b);
    setSplit(value);
    saveSplit(value);
  }

  return (
    <Tooltip label="Drag to resize the list and the map" shortcut="Double-click to reset">
      <div
        className="splitter"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the list and the map"
        aria-valuenow={Math.round(split)}
        aria-valuemin={0}
        aria-valuemax={100}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onKeyDown={onKeyDown}
        onDoubleClick={() => {
          setSplit(50);
          saveSplit(50);
        }}
      >
        <span className="splitter-line" aria-hidden="true" />
      </div>
    </Tooltip>
  );
}

function EmptyState({ stateFilter, filtered, onClear }) {
  if (filtered) {
    return (
      <div className="empty">
        <Icon icon={icons.search} size={24} />
        <p className="empty-title">No matching alerts</p>
        <p className="empty-text">Try another type or search.</p>
        <button type="button" className="btn btn-secondary" onClick={onClear}>
          Clear filters
        </button>
      </div>
    );
  }
  const text = {
    action: ["No open alerts", "Everything is quiet."],
    acknowledged: ["No acknowledged alerts", "Alerts stay here after someone acknowledges them, until they are resolved."],
    all: ["No alerts yet", "Alerts show up here as soon as a Fob sends one."],
  }[stateFilter];
  return (
    <div className="empty">
      <Icon icon={icons.inbox} size={24} />
      <p className="empty-title">{text[0]}</p>
      <p className="empty-text">{text[1]}</p>
    </div>
  );
}

export default function LivePage(props) {
  const {
    alerts, // filtered and sorted; null while loading
    loadFailed,
    view,
    setView,
    typeFilter,
    setTypeFilter,
    stateFilter,
    setStateFilter,
    query,
    setQuery,
    searchOpen,
    setSearchOpen,
    searchInputRef,
    settings,
    update,
    theme,
    config,
    configLoaded,
    nowServer,
    highlightedId, // hovered row or marker: lights up the marker and shows its circle
    selectedRowId, // its Peek is open, or its marker is hovered
    selectedId, // its Peek is open: the map shows its circle too
    onRowHover,
    onMarkerHover,
    onOpen,
    onAck,
    flyTarget,
    panelCollapsed,
    togglePanel,
    registerFocus,
    split,
    setSplit,
    saveSplit,
  } = props;
  const bodyRef = useRef(null);

  const filtered = typeFilter !== "ALL" || query.trim() !== "";
  const clear = () => {
    setTypeFilter("ALL");
    setQuery("");
    setSearchOpen(false);
  };

  const table =
    alerts === null ? (
      <p className="loading">{loadFailed ? "Waiting for the server." : "Loading alerts."}</p>
    ) : alerts.length === 0 ? (
      <EmptyState stateFilter={stateFilter} filtered={filtered} onClear={clear} />
    ) : (
      <AlertTable
        alerts={alerts}
        grouped={stateFilter === "all"}
        showStatus={stateFilter !== "action" && view !== "split"}
        compact={view === "split"}
        nowServer={nowServer}
        timeFormat={settings.timeFormat}
        selectedId={selectedRowId}
        onOpen={onOpen}
        onAck={onAck}
        onHover={onRowHover}
        registerFocus={registerFocus}
      />
    );

  return (
    <div className="page page--live">
      <header className="page-header">
        <div className="page-head-main">
          <h1 className="page-title">Live</h1>
          <ViewTabs view={view} setView={setView} />
        </div>
        <div className="view-tools">
          <FilterMenu typeFilter={typeFilter} setTypeFilter={setTypeFilter} />
          <SearchBox query={query} setQuery={setQuery} searchOpen={searchOpen} setSearchOpen={setSearchOpen} inputRef={searchInputRef} />
          <Segmented label="Show alerts" value={stateFilter} options={STATE_OPTIONS} onChange={setStateFilter} />
        </div>
      </header>

      <div
        ref={bodyRef}
        id="live-panel"
        role="tabpanel"
        aria-labelledby={"tab-" + view}
        className={"live-body live-body--" + view}
        style={view === "split" ? { "--split": split + "%" } : undefined}
      >
        {view !== "map" && <div className="table-pane">{table}</div>}
        {view === "split" && <Splitter bodyRef={bodyRef} split={split} setSplit={setSplit} saveSplit={saveSplit} />}
        {view !== "list" && (
          <div className="map-pane">
            <AlertMap
              alerts={alerts}
              theme={theme}
              settings={settings}
              update={update}
              cartoKey={config && config.carto_key}
              configLoaded={configLoaded}
              highlightedId={highlightedId}
              selectedId={selectedId}
              selectedRowId={selectedRowId}
              onHover={onMarkerHover}
              onRowHover={onRowHover}
              onOpen={onOpen}
              flyTarget={flyTarget}
              withPanel={view === "map"}
              panelCollapsed={panelCollapsed}
              onTogglePanel={togglePanel}
              nowServer={nowServer}
              registerFocus={registerFocus}
            />
          </div>
        )}
      </div>
    </div>
  );
}
