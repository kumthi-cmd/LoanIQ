/**
 * nav.ts: the screens of LoanIQ, grouped and in the order of the desk's workflow.
 *
 * Where it sits: [nav] -> Sidebar (links) and App.tsx (routes).
 *
 * BUSINESS: the sidebar reads like the desk's day, in four groups:
 *   Tape      look at the tape, ask it questions
 *   Price     slot loans into pools, read the price file, find the best execution
 *   Trade     watch the blotter and positions, optimize
 *   Showcase  what LoanIQ is and how it was built AI-first
 *   Screens not built yet are shown but disabled, marked "Planned", so a visitor sees
 *   the whole workflow from the first screen. The number is the roadmap step that
 *   builds the screen (docs/roadmap.md); Showcase pages have none.
 *   Tape Upload (2) and Explorer (3) sit at the end of Trade, after Optimizer, since
 *   Step 4d: they are later development, so the live Tape screens come first and
 *   the planned ones wait at the bottom of the workflow (docs/decisions.md).
 *   An item with agent: true is answered by an AI agent and carries the Agent mark
 *   (components/AgentMark.tsx), so a visitor can see which screen uses Claude.
 *   An item with an action (Step 5b: Product Slotting) is a button that does
 *   something to the Loan Tape instead of opening a screen (docs/decisions.md).
 * TECH: one list drives both the sidebar and the router. A screen becomes live by
 *   setting live: true and adding its route in App.tsx. React Router then swaps the
 *   screen in the page with no reload.
 */

/**
 * One sidebar entry.
 * BUSINESS: agent marks a screen whose answers come from an AI agent (Ask the Tape).
 * TECH: path is the URL; step is the roadmap step (null: none shown). agent is
 *   optional, so every other item leaves it out and reads as false. An action item
 *   has no screen, so it is not live (no route, routes.test.tsx skips it) and its
 *   path is only a unique key.
 */
export interface NavItem {
  label: string;
  path: string;
  step: number | null;
  live: boolean;
  agent?: boolean;
  action?: "product-slotting";
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
      // BUSINESS: live from Step 4b: plain-English questions answered from the tape,
      //   by a Claude agent (Step 4d shows the Agent mark beside it).
      { label: "Ask the Tape", path: "/ask", step: 4, live: true, agent: true },
    ],
  },
  {
    group: "Price",
    items: [
      // BUSINESS: from Step 5b an action on the Loan Tape, not a screen: it opens the
      //   Product Slotting dialog from anywhere (components/SlottingNavButton.tsx).
      { label: "Product Slotting", path: "#product-slotting", step: 5, live: false, action: "product-slotting" },
      // BUSINESS: live from Step 6c: the desk's illustrative TBA price file (prices,
      //   drops and pay-ups), the prices Best Execution will use.
      { label: "Price Grid", path: "/prices", step: 6, live: true },
      { label: "Best Execution", path: "/best-ex", step: 6, live: false },
    ],
  },
  {
    group: "Trade",
    items: [
      { label: "Blotter & Positions", path: "/positions", step: 7, live: false },
      { label: "Optimizer", path: "/optimizer", step: 8, live: false },
      // BUSINESS: later development, moved here in Step 4d (see the header comment).
      { label: "Tape Upload", path: "/upload", step: 2, live: false },
      { label: "Explorer", path: "/explorer", step: 3, live: false },
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
