/**
 * test/setup.ts: runs before every Vitest test file.
 *
 * TECH: adds jest-dom's matchers (toBeInTheDocument, toHaveTextContent, ...) to
 *   expect, and unmounts rendered components after each test so tests stay
 *   independent.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());
