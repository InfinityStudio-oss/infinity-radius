import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/lib/api-client";
import type { TransactionRead } from "@/lib/api-types";

const queryMock = vi.fn();

vi.mock("@/lib/hooks/use-api-query", () => ({
  useApiQuery: (path: string | null) => queryMock(path),
}));

vi.mock("@/lib/hooks/use-access-token", () => ({
  useAccessToken: () => ({ token: "test-token", ready: true }),
}));

import CollectionsPage from "./page";

function transaction(overrides: Partial<TransactionRead> = {}): TransactionRead {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "22222222-2222-2222-2222-222222222222",
    customer_id: null,
    subscription_id: null,
    reference: "col-ce8ef8aa",
    provider_reference: "DIK1X2R6BW",
    collection_transid: "txn-638e8eb6",
    payer_phone_masked: "2557*****101",
    channel: "MPESA-TZ",
    amount: "1000.00",
    currency: "TZS",
    status: "COMPLETED",
    provider_resultcode: "000",
    provider_message: "COMPLETED",
    stk_requested_at: "2026-09-20T05:00:00Z",
    completed_at: "2026-09-20T05:10:00Z",
    failed_at: null,
    created_at: "2026-09-20T05:00:00Z",
    updated_at: "2026-09-20T05:10:00Z",
    ...overrides,
  };
}

/** Routes each hook call by path so list and summary can differ. */
function mockQueries(options: {
  list?: { state: string; data?: unknown; error?: ApiClientError | null };
  summary?: { state: string; data?: unknown };
}) {
  queryMock.mockImplementation((path: string) => {
    const target = path.startsWith("/api/v1/collections/summary")
      ? options.summary
      : options.list;
    return {
      state: target?.state ?? "loading",
      data: target?.data ?? null,
      error: (target as { error?: ApiClientError })?.error ?? null,
      refetch: vi.fn(),
    };
  });
}

const summaryData = {
  success: true,
  data: { total: 3, completed: 1, in_progress: 1, requires_attention: 1, failed: 0, by_status: {} },
};

describe("CollectionsPage", () => {
  beforeEach(() => queryMock.mockReset());

  it("reads the list from the Collection-scoped endpoint, sorted newest first", () => {
    mockQueries({
      list: { state: "loading" },
      summary: { state: "loading" },
    });
    render(<CollectionsPage />);

    const paths = queryMock.mock.calls.map(([p]) => p as string);
    const listPath = paths.find((p) => p.startsWith("/api/v1/collections?"));
    expect(listPath).toBeDefined();
    expect(listPath).toContain("sort=-created_at");
    expect(paths.some((p) => p.startsWith("/api/v1/collections/summary"))).toBe(true);

    // The generic transactions list is deliberately NOT used: it is shared
    // with captive-portal payments, which must never appear here.
    expect(paths.some((p) => p.startsWith("/api/v1/payments"))).toBe(false);

    // No client-side type filtering, and never a provider URL.
    for (const p of paths) {
      expect(p).not.toMatch(/transaction_type=/);
      expect(p).not.toMatch(/selcom/i);
    }
  });

  it("shows a loading state before data arrives", () => {
    mockQueries({ list: { state: "loading" }, summary: { state: "loading" } });
    render(<CollectionsPage />);
    expect(screen.getByText("Collections")).toBeInTheDocument();
    expect(screen.queryByText(/no payments yet/i)).not.toBeInTheDocument();
  });

  it("shows an empty state rather than placeholder rows", () => {
    mockQueries({
      list: {
        state: "success",
        data: { success: true, data: [], meta: { page: 1, page_size: 20, total: 0, total_pages: 0 } },
      },
      summary: { state: "success", data: summaryData },
    });
    render(<CollectionsPage />);
    expect(screen.getByText(/no payments yet/i)).toBeInTheDocument();
  });

  it("renders a real transaction row with its references", () => {
    mockQueries({
      list: {
        state: "success",
        data: {
          success: true,
          data: [transaction()],
          meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
        },
      },
      summary: { state: "success", data: summaryData },
    });
    render(<CollectionsPage />);

    // Scoped to the table: "Completed" is also a summary-card label.
    const table = within(screen.getByRole("table"));
    expect(table.getByText("col-ce8ef8aa")).toBeInTheDocument();
    expect(table.getByText("DIK1X2R6BW")).toBeInTheDocument();
    expect(table.getByText("2557*****101")).toBeInTheDocument();
    expect(table.getByText("Completed")).toBeInTheDocument();
  });

  it("renders an API error state with a retry", () => {
    mockQueries({
      list: { state: "error", error: new ApiClientError("Request failed with 500", 500) },
      summary: { state: "error" },
    });
    render(<CollectionsPage />);
    expect(screen.getByText(/unable to load collections/i)).toBeInTheDocument();
  });

  it("shows summary counts from the aggregate endpoint, not from the loaded page", () => {
    mockQueries({
      list: {
        state: "success",
        // Only one row loaded, but the tenant has three in total.
        data: {
          success: true,
          data: [transaction()],
          meta: { page: 1, page_size: 20, total: 3, total_pages: 1 },
        },
      },
      summary: { state: "success", data: summaryData },
    });
    render(<CollectionsPage />);

    expect(screen.getByText("Total requests")).toBeInTheDocument();
    // 3 total, despite a single row being rendered.
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("marks summary cards unavailable rather than showing zero when the fetch fails", async () => {
    mockQueries({
      list: {
        state: "success",
        data: { success: true, data: [], meta: { page: 1, page_size: 20, total: 0, total_pages: 0 } },
      },
      summary: { state: "success", data: null },
    });
    render(<CollectionsPage />);
    await waitFor(() => expect(screen.getByText("Total requests")).toBeInTheDocument());
    // A failed summary must not be rendered as a confident "0".
    expect(screen.queryByText(/^0$/)).not.toBeInTheDocument();
  });

  it("renders an unknown status in the table without crashing", () => {
    mockQueries({
      list: {
        state: "success",
        data: {
          success: true,
          data: [transaction({ status: "SOME_FUTURE_STATUS" })],
          meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
        },
      },
      summary: { state: "success", data: summaryData },
    });
    render(<CollectionsPage />);
    // Scoped: "Needs review" is also a summary-card label.
    expect(within(screen.getByRole("table")).getByText("Needs review")).toBeInTheDocument();
  });

  it("hides pagination when there is only one page", () => {
    mockQueries({
      list: {
        state: "success",
        data: {
          success: true,
          data: [transaction()],
          meta: { page: 1, page_size: 20, total: 1, total_pages: 1 },
        },
      },
      summary: { state: "success", data: summaryData },
    });
    render(<CollectionsPage />);
    expect(screen.queryByRole("navigation", { name: /pagination/i })).not.toBeInTheDocument();
  });

  it("shows pagination when there is more than one page", () => {
    mockQueries({
      list: {
        state: "success",
        data: {
          success: true,
          data: [transaction()],
          meta: { page: 1, page_size: 20, total: 40, total_pages: 2 },
        },
      },
      summary: { state: "success", data: summaryData },
    });
    render(<CollectionsPage />);
    expect(screen.getByRole("navigation", { name: /pagination/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
  });
});
