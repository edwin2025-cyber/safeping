import { useEffect, useState } from "react";
import { getJson } from "../lib/api.js";
import { presetRange, RANGE_PRESETS, rangeText } from "../lib/dates.js";
import { agoShort } from "../lib/format.js";
import { isEmptyPreview, startEmptyPreview, stopEmptyPreview } from "../lib/preview.js";
import { icons } from "../lib/icons.js";
import { playAlertTone, unlockAudio } from "../lib/sound.js";
import { usePolling } from "../lib/usePolling.js";
import { Segmented, Select, Switch } from "./Controls.jsx";
import { fontRow } from "./FontPicker.jsx"; // temporary font test
import Icon from "./Icon.jsx";
import Modal from "./Modal.jsx";
import { Tag } from "./Tags.jsx";
import Tooltip from "./Tooltip.jsx";

const DOCS_URL = "https://github.com/edwin2025-cyber/safeping/blob/main/docs/dashboard.md#campus-places";
const HEALTH_MS = 30000;
const HEALTH_RANGES = RANGE_PRESETS.filter((p) => p.value !== "custom");
const REASONS = {
  bad_signature: "bad signature",
  replay: "replay",
  unknown_device: "unknown device",
  wrong_role: "wrong role",
  bad_format: "bad format",
  bad_json: "bad JSON",
};

export const SECTIONS = [
  { id: "appearance", group: "Preferences", label: "Appearance", icon: icons.theme, description: "How SafePing looks in this browser." },
  { id: "alerts", group: "Preferences", label: "Alerts", icon: icons.bell, description: "What happens when a new alert arrives." },
  { id: "map", group: "Preferences", label: "Map", icon: icons.map, description: "How the map shows alerts." },
  { id: "camera", group: "Safety", label: "Camera review", icon: icons.camera, description: "The area and time window for SUSPICIOUS alerts." },
  { id: "places", group: "Safety", label: "Campus places", icon: icons.place, description: "Named places that turn GPS points into words staff know." },
  {
    id: "health",
    group: "System",
    label: "Health",
    icon: icons.health,
    description: "Whether the system itself is working: the radio path, rejected messages, Fobs and the reference sensor.",
  },
  { id: "about", group: "System", label: "About", icon: icons.info, description: "Facts about this SafePing server." },
];

/** A value with an optional second line under it, both on the right of a settings row. */
function HealthValue({ tone, icon, children, sub }) {
  return (
    <span className={"health-value" + (tone ? " tone-" + tone : "")}>
      <span className="health-main">
        {icon && <Icon icon={icon} size={14} />}
        {children}
      </span>
      {sub && <span className="health-sub">{sub}</span>}
    </span>
  );
}

/** System health rows (from Overview in v4). Same row style as every other setting. */
function healthRows({ health, preset, setPreset, refMaxAge }) {
  const range = presetRange(preset);
  const rows = [
    {
      section: "health", id: "h-range", name: "Range", desc: "The numbers below cover " + rangeText(range.from, range.to) + ".",
      control: (id) => <Select labelledBy={id} value={preset} options={HEALTH_RANGES} onChange={setPreset} />,
    },
  ];
  const s = health && health.preset === preset ? health.stats : null;
  const loading = <span className="muted">Loading</span>;

  const d = s ? s.delivery || { lora: 0, wifi: 0, unknown: 0 } : null;
  rows.push({
    section: "health", group: "Messages", id: "h-delivery", name: "Delivery",
    desc: "Messages received by link, STATUS check-ins included. Unknown is older alerts and test tools.",
    value: !d ? loading : d.lora + d.wifi + d.unknown === 0 ? <span className="muted">No messages in this range</span> : (
      <span className="health-links">
        <Tag color="lora" icon={icons.lora}>LoRa <span className="num">{d.lora}</span></Tag>
        <Tag color="wifi" icon={icons.wifi}>WiFi <span className="num">{d.wifi}</span></Tag>
        {d.unknown > 0 && <Tag color="unknown" icon={icons.unknownType}>Unknown <span className="num">{d.unknown}</span></Tag>}
      </span>
    ),
  });
  rows.push({
    section: "health", group: "Messages", id: "h-duplicates", name: "Duplicates caught",
    desc: "The server cannot tell a resend from a replay yet. Both count under Rejected messages as replay.",
    value: !s ? loading : s.duplicates === null || s.duplicates === undefined ? <span className="muted">Not tracked</span> : <span className="num">{s.duplicates}</span>,
  });
  const rej = s ? s.rejected : null;
  const reasons = rej ? Object.entries(rej.by_reason).sort((a, b) => b[1] - a[1]) : [];
  const attack = rej && ((rej.by_reason.bad_signature || 0) > 0 || (rej.by_reason.replay || 0) > 0);
  rows.push({
    section: "health", group: "Messages", id: "h-rejected", name: "Rejected messages",
    desc: "Messages the server turned away. Red when any had a bad signature or were a replay.",
    value: !s ? loading : !rej ? <span className="muted">Not tracked</span> : (
      <HealthValue
        tone={attack ? "red" : null}
        icon={attack ? icons.warning : null}
        sub={reasons.length ? reasons.map(([r, n]) => n + " " + (REASONS[r] || r.replaceAll("_", " "))).join(", ") : null}
      >
        <span className="num">{rej.total}</span>
      </HealthValue>
    ),
  });

  const stale = s ? s.stale_fobs || [] : [];
  const low = s ? s.low_battery_fobs || [] : [];
  rows.push({
    section: "health", group: "Fobs", id: "h-stale", name: "Fobs not seen in 24 h",
    desc: "Fobs with no message of any type, STATUS included, in the last 24 hours.",
    value: !s ? loading : (
      <HealthValue tone={stale.length ? "orange" : null} sub={stale.length ? stale.join(", ") : null}>
        <span className="num">{stale.length}</span>
      </HealthValue>
    ),
  });
  rows.push({
    section: "health", group: "Fobs", id: "h-low", name: "Low battery",
    desc: "Fobs whose newest battery reading is under 20%.",
    value: !s ? loading : (
      <HealthValue tone={low.length ? "yellow" : null} sub={low.length ? low.map((f) => f.name + " " + f.pct + "%").join(", ") : null}>
        <span className="num">{low.length}</span>
      </HealthValue>
    ),
  });
  const age = s ? s.reference_age_s : null;
  rows.push({
    section: "health", group: "Floors", id: "h-reference", name: "Reference sensor",
    desc: "The ground floor pressure board. Indoor floors need a reading newer than " + refMaxAge + " s.",
    value: !s ? loading : (
      <HealthValue tone={age === null || age === undefined || age > refMaxAge ? "orange" : null}>
        {age === null || age === undefined ? "No reading" : "Last reading " + agoShort(age)}
      </HealthValue>
    ),
  });
  return rows;
}

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
function buildRows({ settings, effective, update, reset, config, devices, soundNote, testSound, setSound, health }) {
  const hasKey = !!(config && config.carto_key);
  const d = effective.defaults;
  const version = config ? config.version + (config.commit ? " (" + config.commit + ")" : "") : "Loading";
  return [
    ...healthRows(health),
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
    fontRow(), // temporary font test
    {
      section: "alerts", group: "Sound", id: "sound", name: "Alert sound",
      desc: soundNote || "A short tone when a new MEDICAL or SUSPICIOUS alert arrives.",
      control: (id) => (
        <span className="set-inline">
          <button type="button" className="btn btn-secondary" onClick={testSound}>
            <Icon icon={icons.sound} />
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
      section: "about", group: "Testing", id: "empty", name: "Show an empty dashboard",
      desc: "See SafePing as it looks on its first day, with no Fobs, alerts, readings or places, to check that nothing breaks. "
        + "Only this tab, until you exit or close it. Real alerts are hidden while it is on. The server and its data do not change.",
      control: () =>
        isEmptyPreview() ? (
          <button type="button" className="btn btn-secondary" onClick={stopEmptyPreview}>
            Exit preview
          </button>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={startEmptyPreview}>
            Show empty dashboard
          </button>
        ),
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

export default function SettingsModal({
  settings,
  effective,
  update,
  reset,
  config,
  devices,
  refMaxAge = 120,
  onClose,
  returnFocus,
  initialSection = "appearance",
}) {
  const [section, setSection] = useState(initialSection);
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState(null);
  const [soundNote, setSoundNote] = useState(null);

  // Health: /api/stats for the picked range, while Health is open or a search is shown.
  const [healthPreset, setHealthPreset] = useState("7d");
  const [healthStats, setHealthStats] = useState(null); // { preset, stats }
  usePolling(
    () => {
      const preset = healthPreset;
      const r = presetRange(preset);
      getJson("/api/stats?from=" + r.from + "&to=" + r.to)
        .then((stats) => setHealthStats({ preset, stats }))
        .catch(() => {});
    },
    HEALTH_MS,
    section === "health" || query.trim() !== "",
    [healthPreset],
  );

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

  const health = { health: healthStats, preset: healthPreset, setPreset: setHealthPreset, refMaxAge };
  const rows = buildRows({ settings, effective, update, reset, config, devices, soundNote, testSound, setSound, health });
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
          <Icon icon={icons.search} size={14} />
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
                <Icon icon={s.icon} fixed />
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
              <Icon icon={icons.close} />
            </button>
          </Tooltip>
        </div>
        <div className="set-content">{content}</div>
      </div>
    </Modal>
  );
}
