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
 *   - Fonts are self-hosted from the @fontsource packages: Vite copies the font
 *     files into the build, so the app makes no request to an outside font service
 *     and looks the same offline. Inter (400-700) is the interface font; JetBrains
 *     Mono (400, 500) is for loan IDs and code. Only the weights used are imported.
 */
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
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
