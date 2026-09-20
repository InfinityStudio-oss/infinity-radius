import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mutateMock = vi.fn();
const fetchMock = vi.fn();

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    apiMutate: (...args: unknown[]) => mutateMock(...args),
    apiFetch: (...args: unknown[]) => fetchMock(...args),
  };
});

vi.mock("@/lib/hooks/use-access-token", () => ({
  useAccessToken: () => ({ token: "test-token", ready: true }),
}));

import { ApiClientError } from "@/lib/api-client";
import { NewCollectionDialog } from "./new-collection-dialog";

function transaction(overrides: Record<string, unknown> = {}) {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "22222222-2222-2222-2222-222222222222",
    customer_id: null,
    subscription_id: null,
    reference: "col-abc123",
    provider_reference: null,
    collection_transid: "txn-abc123",
    payer_phone_masked: "2557*****101",
    channel: null,
    amount: "1000.00",
    currency: "TZS",
    status: "STK_SENT",
    provider_resultcode: "000",
    provider_message: "Wallet push successful",
    stk_requested_at: "2026-09-20T05:00:00Z",
    completed_at: null,
    failed_at: null,
    created_at: "2026-09-20T05:00:00Z",
    updated_at: "2026-09-20T05:00:00Z",
    ...overrides,
  };
}

async function fillAndContinue(user: ReturnType<typeof userEvent.setup>, phone = "0762474101") {
  await user.type(screen.getByLabelText(/customer phone number/i), phone);
  await user.type(screen.getByLabelText(/^amount/i), "1000");
  await user.click(screen.getByRole("button", { name: /continue/i }));
}

describe("NewCollectionDialog", () => {
  beforeEach(() => {
    mutateMock.mockReset();
    fetchMock.mockReset();
  });

  it("renders nothing while closed", () => {
    const { container } = render(
      <NewCollectionDialog open={false} onOpenChange={() => {}} onCreated={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("rejects an invalid phone number before any request is made", async () => {
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await user.type(screen.getByLabelText(/customer phone number/i), "12345");
    await user.type(screen.getByLabelText(/^amount/i), "1000");
    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/valid tanzanian mobile number/i);
    expect(mutateMock).not.toHaveBeenCalled();
  });

  it.each([
    ["zero", "0"],
    ["negative", "-5"],
    ["non-numeric", "abc"],
  ])("rejects a %s amount before any request is made", async (_label, amount) => {
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await user.type(screen.getByLabelText(/customer phone number/i), "0762474101");
    await user.type(screen.getByLabelText(/^amount/i), amount);
    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(mutateMock).not.toHaveBeenCalled();
  });

  it("shows a confirmation naming the normalized phone and amount", async () => {
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await fillAndContinue(user);

    // Typed as 07…, confirmed as the canonical 255… form.
    expect(screen.getByText(/255762474101/)).toBeInTheDocument();
    expect(screen.getByText(/TZS\s*1,000/)).toBeInTheDocument();
    expect(mutateMock).not.toHaveBeenCalled();
  });

  it("sends exactly one request with a normalized phone and decimal-string amount", async () => {
    mutateMock.mockResolvedValue({ success: true, data: transaction() });
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await fillAndContinue(user);
    await user.click(screen.getByRole("button", { name: /send payment request/i }));

    await waitFor(() => expect(mutateMock).toHaveBeenCalledTimes(1));
    const [path, options] = mutateMock.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(path).toBe("/api/v1/collections");
    expect(options.body).toEqual({
      amount: "1000.00",
      currency: "TZS",
      phone: "255762474101",
    });
    expect(typeof options.body.amount).toBe("string");
  });

  it("includes the description only when one was typed", async () => {
    mutateMock.mockResolvedValue({ success: true, data: transaction() });
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await user.type(screen.getByLabelText(/customer phone number/i), "0762474101");
    await user.type(screen.getByLabelText(/^amount/i), "1000");
    await user.type(screen.getByLabelText(/description/i), "Router deposit");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(screen.getByRole("button", { name: /send payment request/i }));

    await waitFor(() => expect(mutateMock).toHaveBeenCalledTimes(1));
    const [, options] = mutateMock.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(options.body.description).toBe("Router deposit");
  });

  it("never issues a second request when the confirm button is double-clicked", async () => {
    // A slow response is the dangerous case: without the guard, a second
    // click would charge the customer twice.
    let resolve: ((value: unknown) => void) | undefined;
    mutateMock.mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await fillAndContinue(user);
    const send = screen.getByRole("button", { name: /send payment request/i });
    await user.click(send);
    await user.click(send);
    await user.click(send);

    expect(mutateMock).toHaveBeenCalledTimes(1);
    resolve?.({ success: true, data: transaction() });
  });

  it("disables the confirm button while the request is in flight", async () => {
    mutateMock.mockImplementation(() => new Promise(() => {}));
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await fillAndContinue(user);
    await user.click(screen.getByRole("button", { name: /send payment request/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled(),
    );
  });

  it("shows operator-safe copy for a kill-switch rejection and never names an env var", async () => {
    mutateMock.mockRejectedValue(
      new ApiClientError(
        "Selcom Collection production initiation is not enabled — the second kill switch (SELCOM_COLLECTION_PRODUCTION_ENABLED) is still off",
        422,
      ),
    );
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await fillAndContinue(user);
    await user.click(screen.getByRole("button", { name: /send payment request/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/temporarily unavailable/i);
    expect(alert.textContent).not.toMatch(/SELCOM_COLLECTION_PRODUCTION_ENABLED/);
    expect(alert.textContent).not.toMatch(/kill switch/i);
  });

  it("does not auto-retry after a failure", async () => {
    mutateMock.mockRejectedValue(new ApiClientError("boom", 500));
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await fillAndContinue(user);
    await user.click(screen.getByRole("button", { name: /send payment request/i }));

    await screen.findByRole("alert");
    await new Promise((r) => setTimeout(r, 50));
    expect(mutateMock).toHaveBeenCalledTimes(1);
  });

  it("switches to tracking and shows the status message once created", async () => {
    mutateMock.mockResolvedValue({ success: true, data: transaction() });
    const onCreated = vi.fn();
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={onCreated} />);

    await fillAndContinue(user);
    await user.click(screen.getByRole("button", { name: /send payment request/i }));

    expect(
      await screen.findByText(/payment request sent to the customer's phone/i),
    ).toBeInTheDocument();
    expect(screen.getByText("col-abc123")).toBeInTheDocument();
    expect(onCreated).toHaveBeenCalledTimes(1);
  });

  it("does not show a mobile money reference until the payment is completed", async () => {
    mutateMock.mockResolvedValue({
      success: true,
      data: transaction({ status: "STK_SENT", provider_reference: "DIK1X2R6BW" }),
    });
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await fillAndContinue(user);
    await user.click(screen.getByRole("button", { name: /send payment request/i }));

    await screen.findByText(/sent to the customer's phone/i);
    expect(screen.queryByText(/mobile money reference/i)).not.toBeInTheDocument();
  });

  it("never sends a request directly to a provider URL", async () => {
    mutateMock.mockResolvedValue({ success: true, data: transaction() });
    const user = userEvent.setup();
    render(<NewCollectionDialog open onOpenChange={() => {}} onCreated={() => {}} />);

    await fillAndContinue(user);
    await user.click(screen.getByRole("button", { name: /send payment request/i }));

    await waitFor(() => expect(mutateMock).toHaveBeenCalled());
    for (const [path] of mutateMock.mock.calls as [string][]) {
      expect(path).toMatch(/^\/api\/v1\//);
      expect(path).not.toMatch(/selcom/i);
    }
  });
});
