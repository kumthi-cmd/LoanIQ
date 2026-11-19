/**
 * nav.ts: the screens of LoanIQ, in the order of the desk's workflow.
 *
 * Where it sits: [nav] -> Sidebar (links) and App.tsx (routes).
 *
 * BUSINESS: the sidebar reads like the desk's day: look at the tape, explore it,
 *   slot loans into pools, price them, watch positions, optimize. Screens not built
 *   yet are shown greyed out with their roadmap step (docs/roadmap.md), so a visitor
 *   sees the whole workflow from the first screen.
 * TECH: one list drives both the sidebar and the router. A screen becomes live by
 *   setting live: true and adding its route in App.tsx. React Router then swaps the
 *   screen in the page with no reload.
 */

/** One sidebar entry. TECH: path is the URL; step is the roadmap step that builds it. */
export interface NavItem {
  label: string;
  path: string;
  step: number;
  live: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Loan Tape", path: "/", step: 1, live: true },
  { label: "Tape Upload", path: "/upload", step: 2, live: false },
  { label: "Explorer", path: "/explorer", step: 3, live: false },
  { label: "Ask the Tape", path: "/ask", step: 4, live: false },
  { label: "Slotting", path: "/slotting", step: 5, live: false },
  { label: "Best Execution", path: "/best-ex", step: 6, live: false },
  { label: "Blotter & Positions", path: "/positions", step: 7, live: false },
  { label: "Optimizer", path: "/optimizer", step: 8, live: false },
  { label: "About", path: "/about", step: 1, live: false },
  { label: "How it was built", path: "/how-it-was-built", step: 1, live: false },
];
