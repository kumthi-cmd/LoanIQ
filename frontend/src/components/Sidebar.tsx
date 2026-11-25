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
 *   "Tape, list, 2 items".
 *   An agent item (nav.ts agent: true) gets the Agent mark as its own button right
 *   after the link, in the same row, never inside it: a button inside a link is
 *   invalid HTML, and a click on the mark would also navigate. The link's name then
 *   says so: "Ask the Tape, agent".
 *   An action item (Step 5b: Product Slotting) is a button, drawn by
 *   SlottingNavButton, that opens the run dialog instead of a screen.
 */
import { NavLink } from "react-router";
import { askTheTapeContent } from "../content/content";
import { NAV_GROUPS, type NavItem } from "../nav";
import { AgentMark } from "./AgentMark";
import { SlottingNavButton } from "./SlottingNavButton";

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
 * BUSINESS: a live screen is a link; a planned one says so and cannot be clicked. A
 *   screen answered by an AI agent also carries the Agent mark.
 * TECH: placeholders are plain text with aria-disabled, so they are not focusable
 *   links and the keyboard skips them. For an agent item, aria-label adds ", agent"
 *   to the link's name (the visible text stays the label); the row (.nav-row) keeps
 *   link and mark on one line and carries the hover and current-page background.
 */
function NavEntry({ item }: { item: NavItem }) {
  if (item.action === "product-slotting") return <SlottingNavButton step={item.step} />;
  if (item.live) {
    const link = (
      <NavLink to={item.path} end className="nav-link"
        aria-label={item.agent ? `${item.label}${askTheTapeContent.agentMark.linkSuffix}` : undefined}>
        <StepNumber step={item.step} />
        {item.label}
      </NavLink>
    );
    if (!item.agent) return link;
    return (
      <div className="nav-row">
        {link}
        <AgentMark />
      </div>
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
