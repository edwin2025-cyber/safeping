import { useEffect, useState } from "react";
import { Bell, Info, MapPin, Map as MapIcon, Palette, Search, Video, Volume2, X } from "lucide-react";
import { getJson } from "../lib/api.js";
import { playAlertTone, unlockAudio } from "../lib/sound.js";
import { Segmented, Select, Switch } from "./Controls.jsx";
import Modal from "./Modal.jsx";
import Tooltip from "./Tooltip.jsx";

const ICON = { size: 16, strokeWidth: 1.75, "aria-hidden": true };
const DOCS_URL = "https://github.com/edwin2025-cyber/safeping/blob/main/docs/dashboard.md#campus-places";

export const SECTIONS = [
  { id: "appearance", group: "Preferences", label: "Appearance", Icon: Palette, description: "How SafePing looks in this browser." },
  { id: "alerts", group: "Preferences", label: "Alerts", Icon: Bell, description: "What happens when a new alert arrives." },
  { id: "map", group: "Preferences", label: "Map", Icon: MapIcon, description: "How the map shows alerts." },
  { id: "camera", group: "Safety", label: "Camera review", Icon: Video, description: "The area and time window for SUSPICIOUS alerts." },
  { id: "places", group: "Safety", label: "Campus places", Icon: MapPin, description: "Named places that turn GPS points into words staff know." },
  { id: "about", group: "System", label: "About", Icon: Info, description: "Facts about this SafePing server." },
];

function Minutes({ value, onChange, labelledBy }) {
  return (
    <span className="minutes">
      <input
        type="number"
        className="input"
        min="0"
        max="60"
        step="1"
        value={value}
        aria-labelledby={labelledBy}
        onChange={(e) => {
          const n = Math.round(Number(e.target.value));
          if (Number.isFinite(n)) onChange(Math.min(60, Math.max(0, n)));
        }}
      />
      <span className="minutes-unit">min</span>
    </span>
  );
}

/** Every setting row, as data, so search can look across sections. */
function buildRows({ settings, effective, update, reset, config, devices, soundNote, testSound, setSound }) {
  const hasKey = !!(config && config.carto_key);
  const d = effective.defaults;
  const version = config ? config.version + (config.commit ? " (" + config.commit + ")" : "") : "Loading";
  return [
    {
      section: "appearance", id: "theme", name: "Theme", desc: "Use system setting follows your computer.",
      control: (id) => (
        <Select labelledBy={id} value={settings.theme} onChange={(v) => update({ theme: v })}
          options={[{ value: "auto", label: "Use system setting" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} />
      ),
    },
    {
      section: "appearance", id: "time", name: "Time format", desc: "How times show in lists, panels and copied text.",
      control: (id) => (
        <Segmented labelledBy={id} value={settings.timeFormat} onChange={(v) => update({ timeFormat: v })}
          options={[{ value: "12", label: "12 h" }, { value: "24", label: "24 h" }]} />
      ),
    },
    {
      section: "alerts", group: "Sound", id: "sound", name: "Alert sound",
      desc: soundNote || "A short tone when a new MEDICAL or SUSPICIOUS alert arrives.",
      control: (id) => (
        <span className="set-inline">
          <button type="button" className="btn btn-secondary" onClick={testSound}>
            <Volume2 {...ICON} />
            Test sound
          </button>
          <Switch labelledBy={id} checked={settings.sound} onChange={setSound} />
        </span>
      ),
    },
    {
      section: "alerts", group: "List", id: "status", name: "Show STATUS check-ins", desc: "One-press check-ins. They never text anyone.",
      control: (id) => <Switch labelledBy={id} checked={settings.showStatus} onChange={(v) => update({ showStatus: v })} />,
    },
    {
      section: "map", id: "zoom", name: "Auto-zoom to new alerts", desc: "Moves the map to each new MEDICAL or SUSPICIOUS alert.",
      control: (id) => <Switch labelledBy={id} checked={settings.autoZoom} onChange={(v) => update({ autoZoom: v })} />,
    },
    {
      section: "map", id: "labels", name: "Map labels",
      desc: hasKey ? "Street and place names on the map." : "Needs a CARTO key. The OpenStreetMap tiles always show labels.",
      control: (id) => <Switch labelledBy={id} checked={settings.mapLabels} disabled={!hasKey} onChange={(v) => update({ mapLabels: v })} />,
    },
    {
      section: "camera", group: "Area", id: "sight", name: "Sight radius",
      desc: "Added to the GPS accuracy to draw the area the student could see. Default " + d.sight_radius_m + " m.",
      control: (id) => (
        <Select labelledBy={id} value={String(effective.sightRadius)} onChange={(v) => update({ sightRadius: Number(v) })}
          options={[25, 50, 100].map((m) => ({ value: String(m), label: m + " m" }))} />
      ),
    },
    {
      section: "camera", group: "Time window", id: "before", name: "Minutes before",
      desc: "How far before the press to start reviewing. Default " + d.camera_before_min + " min.",
      control: (id) => <Minutes labelledBy={id} value={effective.cameraBefore} onChange={(v) => update({ cameraBefore: v })} />,
    },
    {
      section: "camera", group: "Time window", id: "after", name: "Minutes after",
      desc: "How long after the press to keep reviewing. Default " + d.camera_after_min + " min.",
      control: (id) => <Minutes labelledBy={id} value={effective.cameraAfter} onChange={(v) => update({ cameraAfter: v })} />,
    },
    { section: "about", group: "Server", id: "version", name: "Server version", desc: "Version and the code commit it runs from.", value: version },
    {
      section: "about", group: "Server", id: "floor", name: "Pressure per floor", desc: "Set with PA_PER_FLOOR when the server starts.",
      value: config ? config.pa_per_floor + " Pa" : "Loading",
    },
    { section: "about", group: "Server", id: "key", name: "Map key set", desc: "Whether CARTO_KEY is set on the server.", value: config ? (hasKey ? "Yes" : "No") : "Loading" },
    {
      section: "about", group: "Server", id: "devices", name: "Registered devices", desc: "Fobs and Reference boards.",
      value: devices ? String(devices.length) : "Loading",
    },
    {
      section: "about", group: "This browser", id: "reset", name: "Reset settings", desc: "Puts every setting on this page back to its default.",
      control: () => (
        <button type="button" className="btn btn-secondary" onClick={reset}>
          Reset to defaults
        </button>
      ),
    },
  ];
}

function Row({ row }) {
  const id = "set-" + row.id;
  return (
    <div className="set-row">
      <div className="set-text">
        <div className="set-name" id={id}>
          {row.name}
        </div>
        <div className="set-desc">{row.desc}</div>
      </div>
      <div className="set-control num">{row.control ? row.control(id) : <span className="set-value">{row.value}</span>}</div>
    </div>
  );
}

function Rows({ rows }) {
  const out = [];
  let group = null;
  rows.forEach((row) => {
    if (row.group && row.group !== group) {
      group = row.group;
      out.push(
        <h3 key={"g-" + group} className="set-group">
          {group}
        </h3>,
      );
    }
    out.push(<Row key={row.id} row={row} />);
  });
  return <div className="set-rows">{out}</div>;
}

function PlacesTable({ places }) {
  if (places === null) return <p className="loading">Loading places.</p>;
  if (places.length === 0) {
    return (
      <div className="set-note">
        <p>
          No places yet. Add them to <code>server/places.json</code> and they show up here.
        </p>
        <a href={DOCS_URL} target="_blank" rel="noopener noreferrer">
          How to add places
        </a>
      </div>
    );
  }
  return (
    <>
      <p className="set-desc set-note-line">Edit server/places.json to change these.</p>
      <table className="table places-table">
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col" className="right">Latitude</th>
            <th scope="col" className="right">Longitude</th>
          </tr>
        </thead>
        <tbody>
          {places.map((p, i) => (
            <tr key={i}>
              <td>{p.name.charAt(0).toUpperCase() + p.name.slice(1)}</td>
              <td className="num right">{p.lat.toFixed(6)}</td>
              <td className="num right">{p.lon.toFixed(6)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export default function SettingsModal({ settings, effective, update, reset, config, devices, onClose, returnFocus, initialSection = "appearance" }) {
  const [section, setSection] = useState(initialSection);
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState(null);
  const [soundNote, setSoundNote] = useState(null);

  useEffect(() => {
    let stop = false;
    getJson("/api/places")
      .then((d) => !stop && setPlaces(d.places))
      .catch(() => !stop && setPlaces([]));
    return () => {
      stop = true;
    };
  }, []);

  function setSound(on) {
    if (on) unlockAudio(); // this click unlocks audio in the browser
    update({ sound: on });
    setSoundNote(null);
  }
  function testSound() {
    unlockAudio();
    setTimeout(() => setSoundNote(playAlertTone() ? null : "This browser blocked the sound. Click Test sound again."), 60);
  }

  const rows = buildRows({ settings, effective, update, reset, config, devices, soundNote, testSound, setSound });
  const q = query.trim().toLowerCase();
  const current = SECTIONS.find((s) => s.id === section);

  let content;
  if (q) {
    const hits = SECTIONS.map((s) => ({
      s,
      rows: rows.filter(
        (r) => r.section === s.id && (r.name + " " + r.desc + " " + s.label + " " + (r.group || "")).toLowerCase().includes(q),
      ),
      placesHit: s.id === "places" && (s.label + " " + s.description).toLowerCase().includes(q),
    })).filter((h) => h.rows.length || h.placesHit);
    content = (
      <>
        <h2 id="settings-title" className="set-title">
          Search results
        </h2>
        <p className="set-lead">Settings that match "{query.trim()}".</p>
        {hits.length === 0 && <p className="set-lead">Nothing matches. Try another word.</p>}
        {hits.map((h) => (
          <section key={h.s.id} className="set-result">
            <h3 className="set-group">{h.s.label}</h3>
            {h.placesHit && <PlacesTable places={places} />}
            <div className="set-rows">
              {h.rows.map((r) => (
                <Row key={r.id} row={r} />
              ))}
            </div>
          </section>
        ))}
      </>
    );
  } else {
    content = (
      <>
        <h2 id="settings-title" className="set-title">
          {current.label}
        </h2>
        <p className="set-lead">{current.description}</p>
        {section === "places" ? <PlacesTable places={places} /> : <Rows rows={rows.filter((r) => r.section === section)} />}
      </>
    );
  }

  let lastGroup = null;
  return (
    <Modal onClose={onClose} labelledBy="settings-title" className="settings" returnFocus={returnFocus}>
      <aside className="set-nav" aria-label="Settings sections">
        <span className="input-icon set-search">
          <Search {...ICON} />
          <input
            type="search"
            className="input"
            placeholder="Search settings"
            aria-label="Search settings"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </span>
        {SECTIONS.map((s) => {
          const header = s.group !== lastGroup ? s.group : null;
          lastGroup = s.group;
          return (
            <div key={s.id}>
              {header && <div className="set-nav-label">{header}</div>}
              <button
                type="button"
                className={"nav-item" + (!q && section === s.id ? " is-selected" : "")}
                aria-current={!q && section === s.id ? "page" : undefined}
                onClick={() => {
                  setQuery("");
                  setSection(s.id);
                }}
              >
                <s.Icon {...ICON} />
                <span className="nav-text">{s.label}</span>
              </button>
            </div>
          );
        })}
      </aside>
      <div className="set-main">
        <div className="set-close">
          <Tooltip label="Close" shortcut="Esc">
            <button type="button" className="icon-btn" aria-label="Close settings" onClick={onClose}>
              <X {...ICON} />
            </button>
          </Tooltip>
        </div>
        <div className="set-content">{content}</div>
      </div>
    </Modal>
  );
}
