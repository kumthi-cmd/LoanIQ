/**
 * App.tsx: the LoanIQ layout (header, sidebar, screen) and its routes.
 *
 * Where it sits: main.tsx -> [App: router + layout] -> one screen per route.
 *
 * BUSINESS: one frame for the whole workflow. The header always shows the synthetic
 *   data warning and the current row count; the sidebar lists every screen.
 * TECH:
 *   - React Router: routes map URLs to screens. The layout route draws the header
 *     and sidebar once; <Outlet /> is where the current screen goes. Moving between
 *     screens swaps only the Outlet, with no page reload.
 *   - The header's row count belongs to whichever screen has a grid. The layout
 *     owns it with useState and hands setRowCount down through the Outlet's
 *     "context", which screens read with useOutletContext().
 *   - routes is exported so tests can mount it in a memory router (no real URL bar).
 *   - New screens: add an entry here and set live: true in nav.ts.
 */
import { useState } from "react";
import { Outlet, type RouteObject } from "react-router";
import { AppHeader } from "./components/AppHeader";
import { Sidebar } from "./components/Sidebar";
import { AboutScreen } from "./screens/AboutScreen";
import { HowItWasBuiltScreen } from "./screens/HowItWasBuiltScreen";
import { LoanTapeScreen } from "./screens/LoanTapeScreen";
import { NotFoundScreen } from "./screens/NotFoundScreen";

/** TECH: what every screen receives from the layout through the Outlet context. */
export interface LayoutContext {
  /** BUSINESS: report how many loans match the screen's filter; null clears it. */
  setRowCount: (count: number | null) => void;
}

/**
 * The page frame around every screen.
 * BUSINESS: header, sidebar, then the screen.
 * TECH: setRowCount from useState is stable across redraws, so screens can list it
 *   as an effect dependency without re-running the effect.
 */
export function Layout() {
  const [rowCount, setRowCount] = useState<number | null>(null);
  const context: LayoutContext = { setRowCount };
  return (
    <div className="app">
      <AppHeader rowCount={rowCount} />
      <div className="app-body">
        <Sidebar />
        <main className="app-main">
          <Outlet context={context} />
        </main>
      </div>
    </div>
  );
}

/**
 * TECH: the route table. "index" is the screen at "/"; "*" catches unknown URLs.
 *   Child paths are relative to "/" ("about" is /about) and must match nav.ts; a
 *   unit test checks every live nav item renders its own screen, not the "*" one.
 */
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <LoanTapeScreen /> },
      // BUSINESS: the Showcase pages, live from Step 1f.
      { path: "about", element: <AboutScreen /> },
      { path: "how-it-was-built", element: <HowItWasBuiltScreen /> },
      { path: "*", element: <NotFoundScreen /> },
    ],
  },
];
