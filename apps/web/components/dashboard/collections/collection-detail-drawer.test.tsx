import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TransactionRead } from "@/lib/api-types";
import { CollectionDetailDrawer } from "./collection-detail-drawer";
import { CollectionStatusBadge } from "./collection-status-badge";

function transaction(overrides: Partial<TransactionRead> = {}): TransactionRead {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "22222222-2222-2222-2222-222222222222",
    customer_id: null,
    subscription_id: null,
    reference: "col-ce8ef8aa",
    provider_reference: null,
    collection_transid: "txn-638e8eb6",
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

describe("CollectionDetailDrawer", () => {
  it("renders nothing without a transaction", () => {
    const { container } = render(
      <CollectionDetailDrawer transaction={null} onClose={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("labels the four identifiers distinctly so they cannot be confused", () => {
    render(
      <CollectionDetailDrawer
        transaction={transaction({ status: "COMPLETED", provider_reference: "DIK1X2R6BW" })}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Infinity Radius Order ID")).toBeInTheDocument();
    expect(screen.getByText("Local Request ID")).toBeInTheDocument();
    expect(screen.getByText("Mobile Money Reference")).toBeInTheDocument();
    expect(screen.getByText("Internal ID")).toBeInTheDocument();

    // And each shows its own distinct value.
    expect(screen.getByText("col-ce8ef8aa")).toBeInTheDocument();
    expect(screen.getByText("txn-638e8eb6")).toBeInTheDocument();
    expect(screen.getByText("DIK1X2R6BW")).toBeInTheDocument();

    // Never a bare ambiguous label.
    expect(screen.queryByText("Transaction ID")).not.toBeInTheDocument();
  });

  it("renders an em dash for a provider reference that does not exist yet", () => {
    render(<CollectionDetailDrawer transaction={transaction()} onClose={() => {}} />);
    const row = screen.getByText("Mobile Money Reference").parentElement;
    expect(row).toHaveTextContent("—");
  });

  it("shows the amount with its currency", () => {
    render(<CollectionDetailDrawer transaction={transaction()} onClose={() => {}} />);
    expect(screen.getByText(/TZS\s*1,000/)).toBeInTheDocument();
  });

  it.each([
    ["COMPLETED", /payment completed successfully/i],
    ["CANCELLED", /payment request was cancelled/i],
    ["USERCANCELLED", /customer cancelled the payment/i],
    ["DECLINED", /payment was declined/i],
    ["REJECTED", /payment was rejected/i],
    ["FAILED", /payment failed/i],
    ["EXPIRED", /payment request expired/i],
    ["PENDING", /waiting for the mobile-money provider/i],
    ["INPROGRESS", /being processed by the mobile-money provider/i],
    ["STK_SENT", /sent to the customer's phone/i],
    ["CREATED", /payment request created/i],
    ["REQUIRES_REVIEW", /taking longer than usual/i],
    ["AMBIGUOUS", /unexpected provider response/i],
  ])("renders the %s status message", (status, expected) => {
    render(
      <CollectionDetailDrawer transaction={transaction({ status })} onClose={() => {}} />,
    );
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("renders an unknown status safely without claiming success", () => {
    render(
      <CollectionDetailDrawer
        transaction={transaction({ status: "SOME_FUTURE_STATUS" })}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/still checking/i)).toBeInTheDocument();
    expect(screen.queryByText(/completed successfully/i)).not.toBeInTheDocument();
    expect(screen.getByText("Needs review")).toBeInTheDocument();
  });

  it("shows completion and failure timestamps only when present", () => {
    render(
      <CollectionDetailDrawer
        transaction={transaction({ status: "COMPLETED", completed_at: "2026-09-20T05:10:00Z" })}
        onClose={() => {}}
      />,
    );
    const completed = screen.getByText("Completed", { selector: "dt" }).parentElement;
    expect(completed).not.toHaveTextContent("—");

    const ended = screen.getByText("Ended", { selector: "dt" }).parentElement;
    expect(ended).toHaveTextContent("—");
  });

  it("never renders the raw payer phone, only the masked form", () => {
    const { container } = render(
      <CollectionDetailDrawer transaction={transaction()} onClose={() => {}} />,
    );
    expect(screen.getByText("2557*****101")).toBeInTheDocument();
    expect(container.textContent).not.toContain("255762474101");
  });
});

describe("CollectionStatusBadge", () => {
  it.each([
    ["COMPLETED", "Completed"],
    ["STK_SENT", "Sent to phone"],
    ["PENDING", "Pending"],
    ["INPROGRESS", "Processing"],
    ["REQUIRES_REVIEW", "Checking"],
    ["AMBIGUOUS", "Checking"],
    ["CANCELLED", "Cancelled"],
    ["USERCANCELLED", "Cancelled by customer"],
    ["DECLINED", "Declined"],
    ["REJECTED", "Rejected"],
    ["FAILED", "Failed"],
    ["EXPIRED", "Expired"],
    ["CREATED", "Created"],
  ])("renders %s as %s", (status, label) => {
    render(<CollectionStatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("renders an unknown status as a neutral needs-review badge", () => {
    render(<CollectionStatusBadge status="WHAT_IS_THIS" />);
    expect(screen.getByText("Needs review")).toBeInTheDocument();
  });

  it("does not throw on a null status", () => {
    render(<CollectionStatusBadge status={null} />);
    expect(screen.getByText("Needs review")).toBeInTheDocument();
  });
});
