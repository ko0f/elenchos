import { NavLink, Outlet } from "react-router-dom";
import { ProviderHealth } from "./ProviderHealth";
import "./Layout.css";

export function Layout() {
  return (
    <div className="layout">
      <header className="layout__header">
        <NavLink to="/benchmarks" className="layout__brand">
          Elenchos
        </NavLink>
        <nav className="layout__nav">
          <NavLink
            to="/benchmarks"
            className={({ isActive }) =>
              `layout__nav-link${isActive ? " layout__nav-link--active" : ""}`
            }
          >
            Benchmarks
          </NavLink>
          <NavLink
            to="/runs"
            className={({ isActive }) =>
              `layout__nav-link${isActive ? " layout__nav-link--active" : ""}`
            }
          >
            Runs
          </NavLink>
          <NavLink
            to="/prompt"
            className={({ isActive }) =>
              `layout__nav-link${isActive ? " layout__nav-link--active" : ""}`
            }
          >
            Prompt
          </NavLink>
        </nav>
        <ProviderHealth />
      </header>
      <main className="layout__main">
        <Outlet />
      </main>
    </div>
  );
}
