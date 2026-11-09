import "./SettingsPage.css";
import { useState } from "react";
import { RotateCcw, Volume2 } from "lucide-react";
import { playAlertTone, unlockAudio } from "../lib/sound.js";

function Segmented({ name, legend, value, options, onChange }) {
  return (
    <fieldset className="seg">
      <legend className="visually-hidden">{legend}</legend>
      {options.map((opt) => (
        <label key={opt.value} className="seg-option">
          <input
            type="radio"
            name={name}
            value={opt.value}
            checked={String(value) === String(opt.value)}
            onChange={() => onChange(opt.value)}
          />
          <span>{opt.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

function Switch({ id, checked, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      className="switch"
      aria-checked={checked}
      aria-labelledby={id}
      onClick={() => onChange(!checked)}
    />
  );
}

function Setting({ id, title, description, children }) {
  return (
    <div className="setting">
      <div className="setting-text">
        <h3 id={id}>{title}</h3>
        {description && <p>{description}</p>}
      </div>
      <div className="setting-control">{children}</div>
    </div>
  );
}

function Minutes({ label, value, onChange }) {
  return (
    <label className="minutes">
      <input
        type="number"
        min="0"
        max="60"
        step="1"
        value={value}
        onChange={(e) => {
          const n = Math.round(Number(e.target.value));
          if (Number.isFinite(n)) onChange(Math.min(60, Math.max(0, n)));
        }}
      />
      <span>{label}</span>
    </label>
  );
}

export default function SettingsPage({ settings, effective, update, reset, hasCartoKey }) {
  const [soundNote, setSoundNote] = useState(null);

  function setSound(on) {
    if (on) unlockAudio(); // this click unlocks audio in the browser
    update({ sound: on });
    setSoundNote(null);
  }

  function testSound() {
    unlockAudio();
    // The audio context can take a moment to start after the first click.
    setTimeout(() => {
      setSoundNote(playAlertTone() ? null : "This browser blocked the sound. Click Test sound again.");
    }, 60);
  }

  return (
    <div className="settings">
      <p className="settings-intro">Settings are saved in this browser and apply right away.</p>

      <section className="settings-group" aria-labelledby="group-display">
        <h2 id="group-display">Display</h2>
        <Setting id="set-theme" title="Theme" description="Auto follows your computer's setting.">
          <Segmented
            name="theme"
            legend="Theme"
            value={settings.theme}
            onChange={(v) => update({ theme: v })}
            options={[
              { value: "auto", label: "Auto" },
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
            ]}
          />
        </Setting>
        <Setting id="set-time" title="Time format">
          <Segmented
            name="timeFormat"
            legend="Time format"
            value={settings.timeFormat}
            onChange={(v) => update({ timeFormat: v })}
            options={[
              { value: "12", label: "12 h" },
              { value: "24", label: "24 h" },
            ]}
          />
        </Setting>
        <Setting id="set-status" title="Show STATUS check-ins" description="One-press check-ins. They never text anyone.">
          <Switch id="set-status" checked={settings.showStatus} onChange={(v) => update({ showStatus: v })} />
        </Setting>
      </section>

      <section className="settings-group" aria-labelledby="group-alerts">
        <h2 id="group-alerts">Alerts</h2>
        <Setting
          id="set-sound"
          title="Alert sound"
          description="Plays a short tone when a new MEDICAL or SUSPICIOUS alert arrives."
        >
          <div className="inline">
            <button type="button" className="btn" onClick={testSound}>
              <Volume2 size={16} aria-hidden="true" />
              Test sound
            </button>
            <Switch id="set-sound" checked={settings.sound} onChange={setSound} />
          </div>
        </Setting>
        {soundNote && <p className="settings-note">{soundNote}</p>}
      </section>

      <section className="settings-group" aria-labelledby="group-map">
        <h2 id="group-map">Map</h2>
        <Setting id="set-zoom" title="Auto-zoom to new alerts" description="Moves the map to each new MEDICAL or SUSPICIOUS alert.">
          <Switch id="set-zoom" checked={settings.autoZoom} onChange={(v) => update({ autoZoom: v })} />
        </Setting>
        <Setting
          id="set-labels"
          title="Map labels"
          description={hasCartoKey ? "Street and place names on the map." : "Needs a CARTO key. The OpenStreetMap tiles always show labels."}
        >
          <Switch id="set-labels" checked={settings.mapLabels} onChange={(v) => update({ mapLabels: v })} />
        </Setting>
        <Setting
          id="set-sight"
          title="Sight radius for SUSPICIOUS"
          description={"Added to the GPS accuracy to draw the area the student could see. Default " + effective.defaults.sight_radius_m + " m."}
        >
          <Segmented
            name="sight"
            legend="Sight radius"
            value={effective.sightRadius}
            onChange={(v) => update({ sightRadius: Number(v) })}
            options={[
              { value: 25, label: "25 m" },
              { value: 50, label: "50 m" },
              { value: 100, label: "100 m" },
            ]}
          />
        </Setting>
        <Setting
          id="set-camera"
          title="Camera review window"
          description={
            "Minutes before and after a SUSPICIOUS alert to check the cameras. Default " +
            effective.defaults.camera_before_min + " before, " + effective.defaults.camera_after_min + " after."
          }
        >
          <div className="inline">
            <Minutes label="min before" value={effective.cameraBefore} onChange={(v) => update({ cameraBefore: v })} />
            <Minutes label="min after" value={effective.cameraAfter} onChange={(v) => update({ cameraAfter: v })} />
          </div>
        </Setting>
      </section>

      <div className="settings-foot">
        <button type="button" className="btn" onClick={reset}>
          <RotateCcw size={16} aria-hidden="true" />
          Reset to defaults
        </button>
      </div>
    </div>
  );
}
