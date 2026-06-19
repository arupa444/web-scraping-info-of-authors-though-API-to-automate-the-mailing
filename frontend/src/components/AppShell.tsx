import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/contacts", label: "Contacts" },
  { to: "/lists", label: "Lists" },
  { to: "/segments", label: "Segments" },
  { to: "/campaigns", label: "Campaigns" },
  { to: "/templates", label: "Templates" },
  { to: "/automations", label: "Automations" },
  { to: "/settings", label: "Settings" },
];

export default function AppShell() {
  const { me, logout } = useAuth();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">❄</span>
          <span className="brand-name">iceReach</span>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="ws-mini">{me?.workspace.name}</div>
          <div className="ws-role">{me?.role}</div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-ws">
            <span className="topbar-ws-name">{me?.workspace.name}</span>
            <span className="topbar-ws-slug">{me?.workspace.slug}</span>
          </div>
          <div className="topbar-right">
            <span className="topbar-user">{me?.user.email}</span>
            <button className="btn btn-ghost" onClick={() => logout()}>
              Log out
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
