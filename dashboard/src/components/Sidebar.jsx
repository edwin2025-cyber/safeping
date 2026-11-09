import { useRef, useState } from "react";
import { Activity, Cpu, LayoutDashboard, LogOut, PanelLeftClose, PanelLeftOpen, Search, Settings, ShieldCheck } from "lucide-react";
import Popover from "./Popover.jsx";
import Tooltip from "./Tooltip.jsx";

const ICON = { size: 16, strokeWidth: 1.75, "aria-hidden": true };

export const PAGES = [
  { id: "overview", label: "Overview", Icon: LayoutDashboard },
  { id: "live", label: "Live", Icon: Activity },
  { id: "devices", label: "Devices", Icon: Cpu },
];

/** Wraps a sidebar control in a tooltip only when the sidebar is icon-only. */
function MaybeTip({ show, label, shortcut, children }) {
  return show ? (
    <Tooltip label={label} shortcut={shortcut}>
      {children}
    </Tooltip>
  ) : (
    children
  );
}

export default function Sidebar({ page, collapsed, onToggle, openCount, hasOpenMedical, serverOk, onSearch, onOpenSettings }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const accountRef = useRef(null);
  const settingsRef = useRef(null);

  return (
    <nav className={"sidebar" + (collapsed ? " is-collapsed" : "")} aria-label="Main">
      <div className="sb-top">
        <div className="sb-brand">
          <span className="app-mark" aria-hidden="true">
            <ShieldCheck size={16} strokeWidth={1.75} />
          </span>
          <span className="sb-label sb-brand-name">SafePing</span>
        </div>
        <Tooltip label={collapsed ? "Open sidebar" : "Close sidebar"} shortcut="Ctrl+\">
          <button
            type="button"
            className="icon-btn icon-btn-sm sb-toggle"
            onClick={onToggle}
            aria-label={collapsed ? "Open sidebar" : "Close sidebar"}
            aria-keyshortcuts="Control+\"
          >
            {collapsed ? <PanelLeftOpen {...ICON} /> : <PanelLeftClose {...ICON} />}
          </button>
        </Tooltip>
      </div>

      <MaybeTip show={collapsed} label="Search" shortcut="Ctrl+K">
        <button type="button" className="sb-search" onClick={onSearch} aria-label="Search alerts" aria-keyshortcuts="Control+K">
          <Search {...ICON} />
          <span className="sb-label sb-search-text">Search</span>
          <kbd className="sb-label">Ctrl+K</kbd>
        </button>
      </MaybeTip>

      <div className="sb-section">
        <div className="sb-section-label sb-label">Monitor</div>
        <ul>
          {PAGES.map(({ id, label, Icon }) => {
            const count = id === "live" ? openCount : 0;
            return (
              <li key={id}>
                <MaybeTip show={collapsed} label={label}>
                  <a
                    href={"#/" + id}
                    className={"nav-item" + (page === id ? " is-selected" : "")}
                    aria-current={page === id ? "page" : undefined}
                    aria-label={count ? label + ", " + count + " open" : label}
                  >
                    <Icon {...ICON} />
                    <span className="sb-label nav-text">{label}</span>
                    {count > 0 && (
                      <span className={"nav-count num" + (hasOpenMedical ? " is-urgent" : "")} aria-hidden="true">
                        {count}
                      </span>
                    )}
                  </a>
                </MaybeTip>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="sb-section">
        <div className="sb-section-label sb-label">Workspace</div>
        <ul>
          <li>
            <MaybeTip show={collapsed} label="Settings">
              <button
                ref={settingsRef}
                type="button"
                className="nav-item"
                aria-label="Settings"
                aria-haspopup="dialog"
                onClick={() => onOpenSettings(settingsRef.current)}
              >
                <Settings {...ICON} />
                <span className="sb-label nav-text">Settings</span>
              </button>
            </MaybeTip>
          </li>
        </ul>
      </div>

      <div className="sb-bottom">
        <MaybeTip show={collapsed} label={serverOk ? "Server online" : "Server not reachable"}>
          <div className="sb-server" tabIndex={collapsed ? 0 : undefined} role="status" aria-label={serverOk ? "Server online" : "Server not reachable"}>
            <span className={"dot dot--" + (serverOk ? "green" : "orange")} aria-hidden="true" />
            <span className="sb-label">{serverOk ? "Server online" : "Server not reachable"}</span>
          </div>
        </MaybeTip>
        <MaybeTip show={collapsed} label="Safety office">
          <button
            ref={accountRef}
            type="button"
            className="sb-account"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-label="Account: Safety office. Login coming soon"
            onClick={() => setMenuOpen((o) => !o)}
          >
            <span className="avatar" aria-hidden="true">
              SO
            </span>
            <span className="sb-label sb-account-text">
              <span className="sb-account-name">Safety office</span>
              <span className="sb-account-note">Login coming soon</span>
            </span>
          </button>
        </MaybeTip>
        <Popover anchor={accountRef.current} open={menuOpen} onClose={() => setMenuOpen(false)} label="Account" placement="top-start">
          <div className="popover-title">Safety office</div>
          <button
            type="button"
            role="menuitem"
            className="menu-item"
            onClick={() => {
              setMenuOpen(false);
              onOpenSettings(accountRef.current);
            }}
          >
            <Settings {...ICON} />
            Settings
          </button>
          <div className="menu-divider" role="separator" />
          <Tooltip label="Login coming soon">
            <button type="button" role="menuitem" className="menu-item" aria-disabled="true">
              <LogOut {...ICON} />
              Log out
            </button>
          </Tooltip>
        </Popover>
      </div>
    </nav>
  );
}
