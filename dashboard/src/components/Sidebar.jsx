import { Activity, Cpu, PanelLeftClose, PanelLeftOpen, Settings, ShieldCheck } from "lucide-react";

export const PAGES = [
  { id: "live", label: "Live", Icon: Activity },
  { id: "devices", label: "Devices", Icon: Cpu },
  { id: "settings", label: "Settings", Icon: Settings },
];

export default function Sidebar({ page, collapsed, onToggle }) {
  return (
    <nav className={"sidebar" + (collapsed ? " sidebar--collapsed" : "")} aria-label="Main">
      <div className="brand">
        <ShieldCheck size={22} aria-hidden="true" className="brand-icon" />
        <span className="brand-name sidebar-label">SafePing</span>
      </div>

      <ul className="nav">
        {PAGES.map(({ id, label, Icon }) => (
          <li key={id}>
            <a
              href={"#/" + id}
              className={"nav-item" + (page === id ? " nav-item--selected" : "")}
              aria-current={page === id ? "page" : undefined}
              aria-label={label}
              title={collapsed ? label : undefined}
            >
              <Icon size={18} aria-hidden="true" />
              <span className="sidebar-label">{label}</span>
            </a>
          </li>
        ))}
      </ul>

      <button
        type="button"
        className="icon-btn sidebar-toggle"
        onClick={onToggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-expanded={!collapsed}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}
      </button>
    </nav>
  );
}
