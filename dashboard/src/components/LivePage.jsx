import "./LivePage.css";
import { Inbox } from "lucide-react";
import AlertCard from "./AlertCard.jsx";
import MainMap from "./MainMap.jsx";
import { TYPE_ORDER } from "../lib/alertMeta.js";

export default function LivePage({
  alerts, // sorted, filtered by type; null while loading
  openCount,
  loadFailed,
  typeFilter,
  setTypeFilter,
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
  cardRefs,
}) {
  const statusHidden = typeFilter === "STATUS" && !settings.showStatus;
  const openShown = (alerts || []).filter((a) => !a.acknowledged).length;

  return (
    <div className="live">
      <section className="live-list" aria-labelledby="alerts-heading">
        <div className="list-head">
          <div className="list-title">
            <h2 id="alerts-heading">Alerts</h2>
            <span className="list-count num" aria-live="polite">
              {openCount} open
            </span>
          </div>
          <div className="list-controls">
            <label className="filter">
              <span className="visually-hidden">Alert type</span>
              <select className="select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                <option value="ALL">All types</option>
                {TYPE_ORDER.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <span className="switch-row">
              <button
                type="button"
                role="switch"
                className="switch"
                aria-checked={settings.showStatus}
                aria-labelledby="status-switch-label"
                onClick={() => update({ showStatus: !settings.showStatus })}
              />
              <span id="status-switch-label">Show STATUS check-ins</span>
            </span>
          </div>
        </div>

        <div className="list-body">
          {alerts === null ? (
            <p className="list-note">{loadFailed ? "Waiting for the server." : "Loading alerts."}</p>
          ) : (
            <>
              {openShown === 0 && (
                <div className="empty">
                  <Inbox size={24} aria-hidden="true" />
                  <p>{statusHidden ? "STATUS check-ins are hidden. Turn on Show STATUS check-ins." : "No open alerts."}</p>
                </div>
              )}
              <ul className="cards">
                {alerts.map((a) => (
                  <li key={a.id}>
                    <AlertCard
                      ref={(node) => {
                        if (node) cardRefs.current.set(a.id, node);
                        else cardRefs.current.delete(a.id);
                      }}
                      alert={a}
                      nowServer={nowServer}
                      onOpen={onOpen}
                      onHover={setHighlightedId}
                    />
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </section>

      <section className="live-map" aria-label="Map of alerts">
        <MainMap
          alerts={alerts}
          theme={theme}
          settings={settings}
          cartoKey={config && config.carto_key}
          configLoaded={configLoaded}
          highlightedId={highlightedId}
          onOpen={onOpen}
          onHover={setHighlightedId}
          flyTarget={flyTarget}
        />
      </section>
    </div>
  );
}
