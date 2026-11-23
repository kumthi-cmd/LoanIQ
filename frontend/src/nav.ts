/**
 * nav.ts: the screens of LoanIQ, grouped and in the order of the desk's workflow.
 *
 * Where it sits: [nav] -> Sidebar (links) and App.tsx (routes).
 *
 * BUSINESS: the sidebar reads like the desk's day, in four groups:
 *   Tape      look at the tape, upload one, explore it, ask it questions
 *   Price     slot loans into pools, find the best execution
 *   Trade     watch the blotter and positions, optimize
 *   Showcase  what LoanIQ is and how it was built AI-first
 *   Screens not built yet are shown but disabled, marked "Planned", so a visitor sees
 *   the whole workflow from the first screen. The number is the roadmap step that
 *   builds the screen (docs/roadmap.md); Showcase pages have none.
 * TECH: one list drives both the sidebar and the router. A screen becomes live by
 *   setting live: true and adding its route in App.tsx. React Router then swaps the
 *   screen in the page with no reload.
 */

/** One sidebar entry. TECH: path is the URL; step is the roadmap step (null: none shown). */
export interface NavItem {
  label: string;
  path: string;
  step: number | null;
  live: boolean;
}

/** One sidebar group. BUSINESS: a stage of the desk's workflow. */
export interface NavGroup {
  group: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    group: "Tape",
    items: [
      { label: "Loan Tape", path: "/", step: 1, live: true },
      { label: "Tape Upload", path: "/upload", step: 2, live: false },
      { label: "Explorer", path: "/explorer", step: 3, live: false },
      { label: "Ask the Tape", path: "/ask", step: 4, live: false },
    ],
  },
  {
    group: "Price",
    items: [
      { label: "Slotting", path: "/slotting", step: 5, live: false },
      { label: "Best Execution", path: "/best-ex", step: 6, live: false },
    ],
  },
  {
    group: "Trade",
    items: [
      { label: "Blotter & Positions", path: "/positions", step: 7, live: false },
      { label: "Optimizer", path: "/optimizer", step: 8, live: false },
    ],
  },
  {
    group: "Showcase",
    items: [
      // BUSINESS: live from Step 1f, so a visitor can read what LoanIQ is and how it
      //   was built from any screen.
      { label: "About", path: "/about", step: null, live: true },
      { label: "How it was built", path: "/how-it-was-built", step: null, live: true },
    ],
  },
];

/** TECH: every item in sidebar order, for code that does not care about groups. */
export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
