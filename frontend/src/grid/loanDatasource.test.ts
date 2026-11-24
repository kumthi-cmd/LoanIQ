/**
 * Tests for grid/loanDatasource.ts and api/client.ts.
 * BUSINESS: each scroll asks the server for exactly one block, the header count is
 *   the server's matching total, and a refused filter is reported to the trader
 *   instead of looking like "no loans match".
 * TECH: fetch is replaced by a Vitest mock (vi.fn), so no server is needed.
 */
import type { IGetRowsParams } from "ag-grid-community";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchSummary } from "../api/client";
import { createLoanDatasource } from "./loanDatasource";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "Bad Request",
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function gridParams(): IGetRowsParams & { done: Promise<void> } {
  let resolve!: () => void;
  const done = new Promise<void>((r) => (resolve = r));
  return {
    startRow: 100,
    endRow: 200,
    sortModel: [{ colId: "current_upb", sort: "desc" }],
    filterModel: { ltv: { filterType: "number", type: "greaterThan", filter: 125 } },
    successCallback: vi.fn(() => resolve()),
    failCallback: vi.fn(() => resolve()),
    context: undefined,
    done,
  } as unknown as IGetRowsParams & { done: Promise<void> };
}

afterEach(() => vi.unstubAllGlobals());

describe("createLoanDatasource", () => {
  it("asks /api/loans for one block with sort and filter, then reports the total", async () => {
    const rows = [{ loan_id: "LN1" }, { loan_id: "LN2" }];
    const fetchMock = mockFetch(200, { rows, total: 1234 });
    const onTotal = vi.fn();
    const params = gridParams();

    createLoanDatasource({ onTotal, onError: vi.fn() }).getRows(params);
    await params.done;

    const url = new URL(fetchMock.mock.calls[0][0], "http://x");
    expect(url.pathname).toBe("/api/loans");
    expect(url.searchParams.get("offset")).toBe("100");
    expect(url.searchParams.get("limit")).toBe("100");
    expect(url.searchParams.get("sort")).toBe("current_upb:desc");
    expect(JSON.parse(url.searchParams.get("filter")!).ltv.filter).toBe(125);
    expect(params.successCallback).toHaveBeenCalledWith(rows, 1234);
    expect(onTotal).toHaveBeenCalledWith(1234);
  });

  it("reports a refused filter with the server's message", async () => {
    mockFetch(400, { detail: "Unsupported number filter type: 'notBlank'" });
    const onError = vi.fn();
    const params = gridParams();

    createLoanDatasource({ onTotal: vi.fn(), onError }).getRows(params);
    await params.done;
    await Promise.resolve();

    expect(params.failCallback).toHaveBeenCalled();
    expect(params.successCallback).not.toHaveBeenCalled();
    expect(onError.mock.calls[0][0].message).toContain("notBlank");
  });
});

describe("api client", () => {
  it("throws ApiError with the status when the server fails", async () => {
    mockFetch(503, null);
    await expect(fetchSummary()).rejects.toMatchObject({ name: "ApiError", status: 503 });
    await expect(fetchSummary()).rejects.toBeInstanceOf(ApiError);
  });
});
