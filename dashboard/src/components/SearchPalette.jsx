import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { getJson } from "../lib/api.js";
import { typeMeta } from "../lib/alertMeta.js";
import { ago, formatDateTime, placeShort, studentName } from "../lib/format.js";
import { icons } from "../lib/icons.js";
import Icon from "./Icon.jsx";
import { TypeIcon } from "./Tags.jsx";

const DEBOUNCE_MS = 120;

/** "Find a student": a centered search over students and alerts. Opened from the
    sidebar or with Ctrl+K. Up and Down move, Enter opens, Esc closes.
    A student opens the Device Peek, an alert opens the Alert Peek. */
export default function SearchPalette({ onClose, onOpenAlert, onOpenDevice, showStatus, nowServer, timeFormat }) {
  const [query, setQuery] = useState("");
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Results update as you type. An answer for an older query is dropped.
  useEffect(() => {
    let stop = false;
    const q = query.trim();
    const timer = setTimeout(
      () => {
        getJson("/api/search?q=" + encodeURIComponent(q) + "&status=" + (showStatus ? "1" : "0"))
          .then((d) => {
            if (stop) return;
            setData(d);
            setFailed(false);
            setActive(0);
          })
          .catch(() => !stop && setFailed(true));
      },
      q ? DEBOUNCE_MS : 0,
    );
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [query, showStatus]);

  useEffect(() => {
    if (inputRef.current) inputRef.current.focus();
  }, []);

  const students = data ? data.students : [];
  const alerts = data ? data.alerts : [];
  const items = [
    ...students.map((s) => ({ kind: "student", key: "s-" + s.device_id, student: s })),
    ...alerts.map((a) => ({ kind: "alert", key: "a-" + a.id, alert: a })),
  ];
  const activeItem = items[Math.min(active, items.length - 1)];

  // Keep the active row in view while moving with the arrow keys.
  useLayoutEffect(() => {
    if (!listRef.current || !activeItem) return;
    const el = listRef.current.querySelector('[data-key="' + activeItem.key + '"]');
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [activeItem]);

  function open(item) {
    if (!item) return;
    if (item.kind === "student") onOpenDevice(item.student.device_id);
    else onOpenAlert(item.alert.id);
  }

  function onKeyDown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onCloseRef.current();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!items.length) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (Math.min(i, items.length - 1) + step + items.length) % items.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      open(activeItem);
    } else if (event.key === "Tab") {
      event.preventDefault(); // focus stays in the search box
    }
  }

  const q = query.trim();
  let body;
  if (!data) {
    body = <p className="palette-empty">{failed ? "Waiting for the server." : "Loading."}</p>;
  } else if (!items.length) {
    body = q ? (
      <p className="palette-empty">Nothing matches "{q}". Try part of a name or a Fob ID.</p>
    ) : (
      <p className="palette-empty">No students or alerts yet. Fobs show up here once they are registered.</p>
    );
  } else {
    body = (
      <>
        {students.length > 0 && (
          <div role="group" aria-labelledby="palette-students">
            <div id="palette-students" className="palette-group-label">
              Students
            </div>
            {students.map((s) => {
              const item = items.find((i) => i.key === "s-" + s.device_id);
              const last = s.last_alert;
              return (
                <div
                  key={item.key}
                  id={"palette-" + item.key}
                  data-key={item.key}
                  role="option"
                  aria-selected={activeItem === item}
                  className="palette-item"
                  onMouseMove={() => activeItem !== item && setActive(items.indexOf(item))}
                  onClick={() => open(item)}
                >
                  <span className="palette-lead" aria-hidden="true">
                    <Icon icon={icons.student} size={14} fixed />
                  </span>
                  <span className="palette-main">
                    <span className="palette-name">{s.student_name || s.device_id}</span>
                    {s.student_name && <span className="palette-sub">{s.device_id}</span>}
                  </span>
                  <span className="palette-meta num">
                    {last ? (
                      <>
                        <TypeIcon type={last.type} size={12} label={"Last alert " + typeMeta(last.type).label} />
                        <span title={formatDateTime(last.time, timeFormat)}>{ago(nowServer - last.time)}</span>
                      </>
                    ) : (
                      <span className="muted">No alerts</span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        )}
        {alerts.length > 0 && (
          <div role="group" aria-labelledby="palette-alerts">
            <div id="palette-alerts" className="palette-group-label">
              Recent alerts
            </div>
            {alerts.map((a) => {
              const item = items.find((i) => i.key === "a-" + a.id);
              const place = placeShort(a);
              return (
                <div
                  key={item.key}
                  id={"palette-" + item.key}
                  data-key={item.key}
                  role="option"
                  aria-selected={activeItem === item}
                  className="palette-item"
                  onMouseMove={() => activeItem !== item && setActive(items.indexOf(item))}
                  onClick={() => open(item)}
                >
                  <span className="palette-lead">
                    <TypeIcon type={a.alert_type} label={typeMeta(a.alert_type).label} />
                  </span>
                  <span className="palette-main">
                    <span className="palette-name">{studentName(a)}</span>
                    <span className="palette-sub">{place || "Unknown place"}</span>
                  </span>
                  <span className="palette-meta num" title={formatDateTime(a.timestamp, timeFormat)}>
                    {ago(nowServer - a.timestamp)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </>
    );
  }

  return createPortal(
    <div
      className="palette-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCloseRef.current();
      }}
    >
      <div className="palette" role="dialog" aria-modal="true" aria-label="Find a student" onKeyDown={onKeyDown}>
        <div className="palette-input-row">
          <Icon icon={icons.search} />
          <input
            ref={inputRef}
            type="text"
            className="palette-input"
            placeholder="Search students or Fob IDs"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-autocomplete="list"
            aria-activedescendant={activeItem ? "palette-" + activeItem.key : undefined}
            aria-label="Search students or Fob IDs"
            autoComplete="off"
            spellCheck="false"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div ref={listRef} id="palette-list" role="listbox" aria-label="Results" className="palette-list">
          {body}
        </div>
        <div className="palette-foot" aria-hidden="true">
          <span>
            <kbd>Up</kbd> <kbd>Down</kbd> to move
          </span>
          <span>
            <kbd>Enter</kbd> to open
          </span>
          <span>
            <kbd>Esc</kbd> to close
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
