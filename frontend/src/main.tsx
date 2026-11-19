/**
 * main.tsx: where the LoanIQ single-page app starts in the browser.
 *
 * Where it sits: index.html -> [main.tsx] -> App.tsx (router, layout, screens).
 *
 * BUSINESS: loads once; every screen after that is drawn without a page reload.
 * TECH:
 *   - AG Grid v33+ is split into modules, and a grid only has the features whose
 *     modules are registered. AllCommunityModule registers every free feature
 *     (Infinite Row Model, filters, tooltips) once for all grids in the app.
 *   - createBrowserRouter reads the screen from the real URL, so a screen can be
 *     bookmarked; FastAPI sends index.html for any screen URL (backend/app/main.py).
 *   - StrictMode is a development-only React check that runs effects twice to
 *     reveal effects that do not clean up after themselves.
 */
import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router";
import { routes } from "./App";
import "./styles.css";

ModuleRegistry.registerModules([AllCommunityModule]);

const router = createBrowserRouter(routes);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
