import { describe, expect, it } from "vitest";
import { isValidTzPhone, maskTzPhone, normalizeTzPhone } from "./phone";
import { normalizeAmount } from "./amount";
import {
  COLLECTION_STATUSES,
  presentCollectionStatus,
  shouldPollCollection,
} from "./status";

describe("Tanzania phone normalization", () => {
  it("normalizes the local 07… format", () => {
    expect(normalizeTzPhone("0762474101")).toEqual({ ok: true, value: "255762474101" });
  });

  it("normalizes the +255… format", () => {
    expect(normalizeTzPhone("+255762474101")).toEqual({ ok: true, value: "255762474101" });
  });

  it("normalizes the bare 255… format", () => {
    expect(normalizeTzPhone("255762474101")).toEqual({ ok: true, value: "255762474101" });
  });

  it("accepts numbers typed with spaces, dashes and parentheses", () => {
    expect(normalizeTzPhone(" +255 (762) 474-101 ")).toEqual({
      ok: true,
      value: "255762474101",
    });
  });

  it.each([
    ["empty", ""],
    ["too short", "07624741"],
    ["too long", "07624741011"],
    ["wrong country code", "+254762474101"],
    ["invalid subscriber prefix", "0862474101"],
    ["letters", "07abcdefgh"],
    ["a landline-shaped number", "0222474101"],
  ])("rejects %s", (_label, input) => {
    const result = normalizeTzPhone(input);
    expect(result.ok).toBe(false);
    expect(isValidTzPhone(input)).toBe(false);
  });

  it("masks a normalized number the same way the backend does", () => {
    expect(maskTzPhone("255762474101")).toBe("2557*****101");
  });
});

describe("amount handling", () => {
  it("normalizes a whole number to two decimals", () => {
    expect(normalizeAmount("1000")).toEqual({ ok: true, value: "1000.00" });
  });

  it("keeps two decimal places as typed", () => {
    expect(normalizeAmount("1000.50")).toEqual({ ok: true, value: "1000.50" });
  });

  it("pads a single decimal place", () => {
    expect(normalizeAmount("1000.5")).toEqual({ ok: true, value: "1000.50" });
  });

  it("accepts a thousands separator the user typed", () => {
    expect(normalizeAmount("1,000")).toEqual({ ok: true, value: "1000.00" });
  });

  it("emits a decimal string, never a number", () => {
    const result = normalizeAmount("1000");
    expect(result.ok).toBe(true);
    if (result.ok) expect(typeof result.value).toBe("string");
  });

  it.each([
    ["zero", "0"],
    ["explicit zero decimals", "0.00"],
    ["negative", "-100"],
    ["empty", ""],
    ["whitespace only", "   "],
    ["non-numeric", "abc"],
    ["three decimal places", "10.123"],
    ["a float expression", "1e3"],
  ])("rejects %s", (_label, input) => {
    expect(normalizeAmount(input).ok).toBe(false);
  });
});

describe("status presentation", () => {
  it("covers every status the backend enum defines", () => {
    for (const status of COLLECTION_STATUSES) {
      const presentation = presentCollectionStatus(status);
      expect(presentation.label).toBeTruthy();
      expect(presentation.message).toBeTruthy();
    }
  });

  it("treats only COMPLETED as paid", () => {
    const paid = COLLECTION_STATUSES.filter((s) => presentCollectionStatus(s).isPaid);
    expect(paid).toEqual(["COMPLETED"]);
  });

  it("keeps polling exactly the non-terminal statuses", () => {
    const polling = COLLECTION_STATUSES.filter((s) => shouldPollCollection(s));
    expect(polling.sort()).toEqual(
      ["AMBIGUOUS", "CREATED", "INPROGRESS", "PENDING", "REQUIRES_REVIEW", "STK_SENT"].sort(),
    );
  });

  it("stops polling once a status is terminal", () => {
    for (const status of ["COMPLETED", "CANCELLED", "USERCANCELLED", "REJECTED", "DECLINED", "FAILED", "EXPIRED"]) {
      expect(shouldPollCollection(status)).toBe(false);
    }
  });

  it("falls back safely for an unknown status without throwing", () => {
    const presentation = presentCollectionStatus("SOME_FUTURE_STATUS");
    expect(presentation.tone).toBe("unknown");
    expect(presentation.isPaid).toBe(false);
    // Still watched, never presented as success or as a plain failure.
    expect(presentation.isPolling).toBe(true);
    expect(presentation.label).toBe("Needs review");
  });

  it("falls back safely for null/undefined/empty status", () => {
    for (const value of [null, undefined, ""]) {
      const presentation = presentCollectionStatus(value);
      expect(presentation.isPaid).toBe(false);
      expect(presentation.tone).toBe("unknown");
    }
  });

  it("never claims money arrived for a non-completed status", () => {
    for (const status of COLLECTION_STATUSES) {
      if (status === "COMPLETED") continue;
      expect(presentCollectionStatus(status).message.toLowerCase()).not.toContain("completed successfully");
    }
  });

  it("distinguishes attention states from outright failure", () => {
    expect(presentCollectionStatus("REQUIRES_REVIEW").tone).toBe("attention");
    expect(presentCollectionStatus("AMBIGUOUS").tone).toBe("attention");
    expect(presentCollectionStatus("FAILED").tone).toBe("failure");
    expect(presentCollectionStatus("COMPLETED").tone).toBe("success");
  });

  it("warns against duplicate requests on AMBIGUOUS", () => {
    expect(presentCollectionStatus("AMBIGUOUS").message).toContain("Do not create a duplicate");
  });
});
