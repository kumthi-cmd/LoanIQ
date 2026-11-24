/**
 * Tests for ask/savedQueries.ts: the last 5 saved queries in localStorage.
 *
 * BUSINESS: protects the "Saved queries · Last 5" panel: newest first, no duplicates,
 *   never more than five, and a screen that still works when the browser blocks
 *   storage or holds something unreadable.
 * TECH: jsdom provides localStorage; a broken one is simulated with vi.spyOn.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { addSaved, findSaved, loadSaved, MAX_SAVED, STORAGE_KEY, storeSaved, tagFor, type SavedQuery } from "./savedQueries";

const q = (n: number): SavedQuery => ({ tag: `Q${n}`, question: `question ${n}`, queries: [{ sql: `SELECT ${n}`, title: `T${n}` }] });

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("addSaved", () => {
  it("keeps the newest five, newest first", () => {
    let list: SavedQuery[] = [];
    for (let n = 1; n <= 7; n += 1) list = addSaved(list, q(n));
    expect(list.map((x) => x.tag)).toEqual(["Q7", "Q6", "Q5", "Q4", "Q3"]);
    expect(list).toHaveLength(MAX_SAVED);
  });

  it("moves a query saved again to the front instead of copying it", () => {
    const list = addSaved(addSaved(addSaved([], q(1)), q(2)), { ...q(1), tag: "renamed" });
    expect(list.map((x) => x.tag)).toEqual(["renamed", "Q2"]);
    expect(findSaved(list, q(1))?.tag).toBe("renamed");
    expect(findSaved(list, q(3))).toBeUndefined();
  });
});

describe("storage", () => {
  it("round-trips through localStorage", () => {
    storeSaved([q(1), q(2)]);
    expect(loadSaved()).toEqual([q(1), q(2)]);
  });

  it("drops malformed entries and reads garbage as empty", () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([q(1), { tag: "x" }, { ...q(2), queries: [] }, 5]));
    expect(loadSaved()).toEqual([q(1)]);
    window.localStorage.setItem(STORAGE_KEY, "{not json");
    expect(loadSaved()).toEqual([]);
  });

  it("keeps working when the browser blocks storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(loadSaved()).toEqual([]);
    expect(() => storeSaved([q(1)])).not.toThrow();
  });
});

describe("tagFor", () => {
  it("uses the first query's title, else the question, cut to 40 characters", () => {
    expect(tagFor("question", [{ sql: "S", title: "LTV > 125" }])).toBe("LTV > 125");
    expect(tagFor("Which loans are in Puerto Rico?", [{ sql: "S", title: "" }])).toBe("Which loans are in Puerto Rico?");
    expect(tagFor("x".repeat(60), [])).toHaveLength(40);
  });
});
