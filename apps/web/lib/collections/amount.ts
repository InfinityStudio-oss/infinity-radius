/**
 * Decimal-safe amount handling for the Collection form.
 *
 * Money is never parsed into a JS number for arithmetic here — floats
 * cannot represent decimal money exactly, and the whole finance layer
 * (Postgres NUMERIC, Python Decimal, the Money string type in
 * packages/types) exists to avoid exactly that. This module only ever
 * validates the SHAPE of a typed string and re-emits it as a canonical
 * decimal string for the API. `Number()` appears once, purely to compare
 * against zero — never to compute a value that is sent or displayed.
 *
 * No minimum or maximum is enforced here: this codebase has no configured
 * Collection limits, and inventing one in the browser would reject
 * payments the backend would happily accept. If the backend ever rejects
 * an amount, the form surfaces that message.
 */

const DECIMAL_SHAPE = /^\d{1,12}(\.\d{1,2})?$/;

export type AmountValidationResult =
  | { ok: true; value: string }
  | { ok: false; reason: string };

/**
 * Validates a user-typed amount and returns it as a canonical
 * two-decimal string (e.g. "1000" -> "1000.00") for the API's Money field.
 */
export function normalizeAmount(raw: string): AmountValidationResult {
  const trimmed = raw.trim().replace(/,/g, "");

  if (trimmed === "") {
    return { ok: false, reason: "Enter an amount." };
  }

  if (!DECIMAL_SHAPE.test(trimmed)) {
    return {
      ok: false,
      reason: "Enter a valid amount using numbers only, with at most 2 decimal places.",
    };
  }

  // Shape is already proven decimal; this comparison is a zero/negative
  // check only and never feeds the value that gets sent.
  if (Number(trimmed) <= 0) {
    return { ok: false, reason: "Amount must be greater than zero." };
  }

  const [whole, fraction = ""] = trimmed.split(".");
  return { ok: true, value: `${whole}.${fraction.padEnd(2, "0")}` };
}

export function isValidAmount(raw: string): boolean {
  return normalizeAmount(raw).ok;
}
