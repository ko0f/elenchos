import { NavLink, Outlet } from "react-router-dom";
import { FaIcon } from "./FaIcon";
import "./Layout.css";

export function Layout() {
  return (
    <div className="layout">
      <header className="layout__header">
        <NavLink to="/" end className="layout__brand">
          <FaIcon icon="scale-balanced" className="layout__brand-icon" />
          Elenchos
        </NavLink>
        <nav className="layout__nav">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `layout__nav-link${isActive ? " layout__nav-link--active" : ""}`
            }
          >
            <FaIcon icon="gauge" className="layout__nav-icon" />
            Dashboard
          </NavLink>
          <NavLink
            to="/benchmarks"
            className={({ isActive }) =>
              `layout__nav-link${isActive ? " layout__nav-link--active" : ""}`
            }
          >
            <FaIcon icon="clipboard-list" className="layout__nav-icon" />
            Benchmarks
          </NavLink>
          <NavLink
            to="/runs"
            className={({ isActive }) =>
              `layout__nav-link${isActive ? " layout__nav-link--active" : ""}`
            }
          >
            <FaIcon icon="play" className="layout__nav-icon" />
            Runs
          </NavLink>
          <NavLink
            to="/prompt"
            className={({ isActive }) =>
              `layout__nav-link${isActive ? " layout__nav-link--active" : ""}`
            }
          >
            <FaIcon icon="message" className="layout__nav-icon" />
            Prompt
          </NavLink>
          <NavLink
            to="/leaderboard"
            className={({ isActive }) =>
              `layout__nav-link${isActive ? " layout__nav-link--active" : ""}`
            }
          >
            <FaIcon icon="trophy" className="layout__nav-icon" />
            Leaderboard
          </NavLink>
        </nav>
      </header>
      <main className="layout__main">
        <Outlet />
      </main>
    </div>
  );
}
