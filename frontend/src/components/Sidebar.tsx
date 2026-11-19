/**
 * components/Sidebar.tsx: the left navigation of LoanIQ.
 *
 * Where it sits: App layout -> [Sidebar] -> screens (React Router).
 *
 * BUSINESS: every screen of the workflow, grouped Tape / Price / Trade / Showcase,
 *   each with the roadmap step that builds it. Live screens are links; screens not
 *   built yet are visible but disabled and tagged "Planned", so a first-time visitor
 *   sees the whole desk flow. The footer says how LoanIQ was built.
 * TECH: NavLink is React Router's link that knows whether it is the current page
 *   (it adds aria-current="page"). Clicking changes the URL and the screen without
 *   reloading the page. "end" on "/" stops it matching every URL. Groups are lists
 *   labelled by their heading (aria-labelledby), so a screen reader announces
 *   "Tape, list, 4 items".
 */
import { NavLink } from "react-router";
import { NAV_GROUPS, type NavItem } from "../nav";

/**
 * The step number column; blank for Showcase pages, so labels still line up.
 * TECH: aria-hidden, so a screen reader says "Loan Tape", not "1Loan Tape"; the
 *   number is a visual cue to the roadmap order, which the list order already gives.
 */
function StepNumber({ step }: { step: number | null }) {
  return (
    <span className="nav-step-no" aria-hidden="true">
      {step ?? ""}
    </span>
  );
}

/**
 * One sidebar entry.
 * BUSINESS: a live screen is a link; a planned one says so and cannot be clicked.
 * TECH: placeholders are plain text with aria-disabled, so they are not focusable
 *   links and the keyboard skips them.
 */
function NavEntry({ item }: { item: NavItem }) {
  if (item.live) {
    return (
      <NavLink to={item.path} end className="nav-link">
        <StepNumber step={item.step} />
        {item.label}
      </NavLink>
    );
  }
  return (
    <span className="nav-link nav-placeholder" aria-disabled="true">
      <StepNumber step={item.step} />
      {item.label}
      <span className="nav-planned">Planned</span>
    </span>
  );
}

/**
 * The sidebar.
 * BUSINESS: a visitor sees the whole desk workflow at a glance.
 * TECH: the heading ids are derived from the group name, which is unique.
 */
export function Sidebar() {
  return (
    <nav className="sidebar" aria-label="Screens">
      {NAV_GROUPS.map((g) => {
        const headingId = `nav-group-${g.group.toLowerCase()}`;
        return (
          <div key={g.group} className="nav-group">
            <div id={headingId} className="nav-group-label">
              {g.group}
            </div>
            <ul aria-labelledby={headingId}>
              {g.items.map((item) => (
                <li key={item.path}>
                  <NavEntry item={item} />
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      <div className="sidebar-foot">
        <span>Built AI-first with Claude Code</span>
        <a className="mono" href="https://github.com/kumthi-cmd/LoanIQ">
          kumthi-cmd/LoanIQ
        </a>
      </div>
    </nav>
  );
}
