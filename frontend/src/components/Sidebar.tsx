/**
 * components/Sidebar.tsx: the left navigation of LoanIQ.
 *
 * Where it sits: App layout -> [Sidebar] -> screens (React Router).
 *
 * BUSINESS: every screen of the workflow in order. Live screens are links; later
 *   screens show which roadmap step brings them.
 * TECH: NavLink is React Router's link that knows whether it is the current page
 *   (it adds aria-current="page"). Clicking changes the URL and the screen without
 *   reloading the page. "end" on "/" stops it matching every URL.
 */
import { NavLink } from "react-router";
import { NAV_ITEMS } from "../nav";

/**
 * The sidebar.
 * BUSINESS: a visitor sees the whole desk workflow at a glance.
 * TECH: placeholders are plain text with aria-disabled, so they are not focusable links.
 */
export function Sidebar() {
  return (
    <nav className="sidebar" aria-label="Screens">
      <ul>
        {NAV_ITEMS.map((item) => (
          <li key={item.path}>
            {item.live ? (
              <NavLink to={item.path} end className="nav-link">
                {item.label}
              </NavLink>
            ) : (
              <span className="nav-link nav-placeholder" aria-disabled="true">
                {item.label}
                <span className="nav-step">Step {item.step}</span>
              </span>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
