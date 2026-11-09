import { useRef, useState } from "react";
import { Check, Columns2, Inbox, ListFilter, Map as MapIcon, Rows3, Search, SearchX, X } from "lucide-react";
import AlertMap from "./AlertMap.jsx";
import AlertTable from "./AlertTable.jsx";
import { Segmented } from "./Controls.jsx";
import Popover from "./Popover.jsx";
import Tooltip from "./Tooltip.jsx";
import { TYPE_ORDER, typeMeta } from "../lib/alertMeta.js";

const ICON = { size: 16, strokeWidth: 1.75, "aria-hidden": true };

export const VIEWS = [
  { id: "split", label: "Split", Icon: Columns2 },
  { id: "list", label: "List", Icon: Rows3 },
  { id: "map", label: "Map", Icon: MapIcon },
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
      {VIEWS.map(({ id, label, Icon }) => (
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
          <Icon {...ICON} />
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
  const label = active ? "Filter: " + typeMeta(typeFilter).label : "Filter by type";
  const options = [{ value: "ALL", label: "All types" }, ...TYPE_ORDER.map((t) => ({ value: t, label: typeMeta(t).label, Icon: typeMeta(t).Icon }))];
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
          <ListFilter {...ICON} />
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
            {o.Icon ? <o.Icon {...ICON} /> : <span className="menu-icon-space" aria-hidden="true" />}
            {o.label}
            {typeFilter === o.value && <Check {...ICON} className="menu-check" />}
          </button>
        ))}
      </Popover>
    </>
  );
}

function SearchBox({ query, setQuery, searchOpen, setSearchOpen, inputRef }) {
  if (!searchOpen && !query) {
    return (
      <Tooltip label="Search" shortcut="Ctrl+K">
        <button type="button" className="icon-btn" aria-label="Search alerts" aria-keyshortcuts="Control+K" onClick={() => setSearchOpen(true)}>
          <Search {...ICON} />
        </button>
      </Tooltip>
    );
  }
  return (
    <span className="input-icon search-box">
      <Search {...ICON} />
      <input
        ref={inputRef}
        type="search"
        className="input"
        placeholder="Student or Fob ID"
        aria-label="Search alerts by student name or Fob ID"
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
            <X {...ICON} />
          </button>
        </Tooltip>
      )}
    </span>
  );
}

function EmptyState({ stateFilter, filtered, onClear }) {
  if (filtered) {
    return (
      <div className="empty">
        <SearchX size={24} strokeWidth={1.75} aria-hidden="true" />
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
      <Inbox size={24} strokeWidth={1.75} aria-hidden="true" />
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
    highlightedId,
    setHighlightedId,
    onOpen,
    flyTarget,
    panelCollapsed,
    togglePanel,
    registerFocus,
  } = props;

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
        showStatus={stateFilter !== "action"}
        compact={view === "split"}
        nowServer={nowServer}
        timeFormat={settings.timeFormat}
        highlightedId={highlightedId}
        onOpen={onOpen}
        onHover={setHighlightedId}
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

      <div id="live-panel" role="tabpanel" aria-labelledby={"tab-" + view} className={"live-body live-body--" + view}>
        {view !== "map" && <div className="table-pane">{table}</div>}
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
              onHover={setHighlightedId}
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
