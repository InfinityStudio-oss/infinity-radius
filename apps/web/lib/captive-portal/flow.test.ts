import { describe, expect, it } from "vitest";
import {
  canRetryPayment,
  formatDuration,
  formatTzs,
  isPlausibleTzSubscriberNumber,
  isTerminalState,
  pollIntervalMs,
  sanitizeSubscriberInput,
  screenStateFor,
  type PaymentStatusResult,
} from "./flow";

function result(overrides: Partial<PaymentStatusResult> = {}): PaymentStatusResult {
  return { status: "pending", ...overrides };
}

describe("screenStateFor", () => {
  it("shows waiting while the payment is undecided", () => {
    expect(screenStateFor(result())).toBe("waiting");
  });

  it("treats under_review as its own state, ahead of everything else", () => {
    // The payment reads as "pending", but it must NOT show the ordinary
    // waiting screen: that one eventually offers a retry, and retrying a
    // payment that may still settle double-charges the customer.
    expect(screenStateFor(result({ status: "pending", under_review: true }))).toBe(
      "under-review",
    );
  });

  it("keeps under_review even if the payment later reads completed", () => {
    expect(
      screenStateFor(result({ status: "completed", under_review: true })),
    ).toBe("under-review");
  });

  it("shows failed for a genuinely failed payment", () => {
    expect(screenStateFor(result({ status: "failed" }))).toBe("failed");
  });

  it("treats an unknown attempt as failed rather than pending forever", () => {
    expect(screenStateFor(result({ status: "not_found" }))).toBe("failed");
  });

  it("shows activating once paid but not yet online", () => {
    expect(
      screenStateFor(result({ status: "completed", activation_status: "pending" })),
    ).toBe("activating");
    expect(
      screenStateFor(result({ status: "completed", activation_status: "activating" })),
    ).toBe("activating");
  });

  it("defaults a paid payment with no activation status to activating, never active", () => {
    expect(screenStateFor(result({ status: "completed" }))).toBe("activating");
  });

  it("shows active only once access genuinely exists", () => {
    expect(
      screenStateFor(result({ status: "completed", activation_status: "active" })),
    ).toBe("active");
  });

  it("distinguishes activation failure from payment failure", () => {
    // The customer HAS paid. Showing this as a payment failure would be
    // both wrong and an invitation to pay twice.
    expect(
      screenStateFor(result({ status: "completed", activation_status: "failed" })),
    ).toBe("activation-failed");
  });
});

describe("canRetryPayment", () => {
  it("allows a deliberate new attempt only after a genuine payment failure", () => {
    expect(canRetryPayment("failed")).toBe(true);
  });

  it("never offers a retry while the payment is under review", () => {
    expect(canRetryPayment("under-review")).toBe(false);
  });

  it("never offers a retry to someone who already paid", () => {
    expect(canRetryPayment("activating")).toBe(false);
    expect(canRetryPayment("active")).toBe(false);
    // Activation is ours to fix — never a reason to charge again.
    expect(canRetryPayment("activation-failed")).toBe(false);
  });

  it("never offers a retry mid-flight", () => {
    expect(canRetryPayment("waiting")).toBe(false);
  });
});

describe("isTerminalState", () => {
  it("keeps polling while waiting or under review", () => {
    expect(isTerminalState("waiting")).toBe(false);
    // Under review can take hours; the screen keeps watching rather than
    // giving up and telling the customer something final.
    expect(isTerminalState("under-review")).toBe(false);
    expect(isTerminalState("activating")).toBe(false);
  });

  it("stops once there is nothing left to learn", () => {
    expect(isTerminalState("active")).toBe(true);
    expect(isTerminalState("failed")).toBe(true);
    expect(isTerminalState("activation-failed")).toBe(true);
  });
});

describe("pollIntervalMs", () => {
  it("stays responsive for the first few checks", () => {
    // Most STK approvals land in seconds.
    expect(pollIntervalMs(1)).toBe(3000);
    expect(pollIntervalMs(3)).toBe(3000);
  });

  it("backs off so an abandoned tab does not hammer the API", () => {
    expect(pollIntervalMs(4)).toBeGreaterThan(3000);
    expect(pollIntervalMs(6)).toBeGreaterThan(pollIntervalMs(4));
  });

  it("caps the interval so a long review still resolves on its own", () => {
    expect(pollIntervalMs(50)).toBe(30000);
    expect(pollIntervalMs(1000)).toBe(30000);
  });
});

describe("phone input", () => {
  it("accepts plausible Tanzanian subscriber numbers", () => {
    expect(isPlausibleTzSubscriberNumber("712345678")).toBe(true);
    expect(isPlausibleTzSubscriberNumber("621111111")).toBe(true);
  });

  it("rejects obviously wrong input", () => {
    expect(isPlausibleTzSubscriberNumber("12345")).toBe(false);
    expect(isPlausibleTzSubscriberNumber("812345678")).toBe(false);
    expect(isPlausibleTzSubscriberNumber("71234567")).toBe(false);
  });

  it("strips non-digits and caps length as the customer types", () => {
    expect(sanitizeSubscriberInput("712 345 678")).toBe("712345678");
    expect(sanitizeSubscriberInput("+255712345678")).toBe("255712345");
    expect(sanitizeSubscriberInput("abc712")).toBe("712");
  });
});

describe("confirmation formatting", () => {
  it("formats a price for the confirmation screen", () => {
    expect(formatTzs("1500.00")).toBe("1,500");
    expect(formatTzs("10000.00")).toBe("10,000");
  });

  it("renders a dash rather than a fake zero when there is no amount", () => {
    expect(formatTzs(null)).toBe("—");
    expect(formatTzs(undefined)).toBe("—");
  });

  it("describes package validity in human terms", () => {
    expect(formatDuration(30)).toBe("30 minutes");
    expect(formatDuration(60)).toBe("1 hour");
    expect(formatDuration(120)).toBe("2 hours");
    expect(formatDuration(1440)).toBe("1 day");
    expect(formatDuration(null)).toBe("No time limit");
  });
});
