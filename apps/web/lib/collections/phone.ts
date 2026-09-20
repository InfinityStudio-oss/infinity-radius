/**
 * Tanzania mobile number normalization for the Collection form.
 *
 * Deliberately mirrors apps/api/app/core/phone.py exactly — same two
 * patterns, same canonical `255XXXXXXXXX` output, same national-numbering
 * shape (9 digits starting 6 or 7, not restricted to a single operator's
 * prefix range since prefixes get ported).
 *
 * This is a UX convenience only: it catches an obvious typo before an STK
 * request is spent on it. The backend re-normalizes and re-validates every
 * number it receives and stays the authority — this never relaxes anything
 * the server would reject.
 */

const LOCAL = /^0([67]\d{8})$/;
const INTERNATIONAL = /^\+?255([67]\d{8})$/;

export type PhoneNormalizationResult =
  | { ok: true; value: string }
  | { ok: false; reason: string };

/** Strips the separators a human might type: spaces, dashes, parentheses. */
function clean(raw: string): string {
  return raw.trim().replace(/[\s\-()]/g, "");
}

/**
 * Normalizes `0762474101`, `+255762474101` or `255762474101` to
 * `255762474101`. Returns a reason instead of throwing so the form can
 * render it inline.
 */
export function normalizeTzPhone(raw: string): PhoneNormalizationResult {
  const cleaned = clean(raw);

  if (cleaned === "") {
    return { ok: false, reason: "Enter the customer's phone number." };
  }

  const local = LOCAL.exec(cleaned);
  if (local) return { ok: true, value: `255${local[1]}` };

  const international = INTERNATIONAL.exec(cleaned);
  if (international) return { ok: true, value: `255${international[1]}` };

  return {
    ok: false,
    reason: "Enter a valid Tanzanian mobile number, e.g. 0762474101 or +255762474101.",
  };
}

export function isValidTzPhone(raw: string): boolean {
  return normalizeTzPhone(raw).ok;
}

/**
 * Masks a normalized number for display where the full number isn't
 * needed. Matches the backend's own masking shape (see
 * apps/api/app/schemas/finance.py._mask_phone) so a masked value coming
 * from the API and one rendered locally look identical.
 */
export function maskTzPhone(phone: string): string {
  if (phone.length <= 7) return phone;
  return `${phone.slice(0, 4)}${"*".repeat(phone.length - 7)}${phone.slice(-3)}`;
}
