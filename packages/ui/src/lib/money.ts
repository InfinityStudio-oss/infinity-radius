/**
 * Formats a decimal-string amount (matching packages/types Money.amount)
 * as localized currency — TZS by default, "TZS 1,500" style via
 * `currencyDisplay: "code"` so the ISO code is always shown, never a
 * symbol ("$") that could be mistaken for a different currency. Returns
 * null when the amount isn't a real, finite number — callers render an
 * em dash or "Unavailable" for that case, never a fabricated 0.
 *
 * DISPLAY ONLY: this never performs money arithmetic — real math stays
 * server-side as Decimal/NUMERIC.
 */
export function formatMoney(
  amount: string | number | null | undefined,
  currency = "TZS",
): string | null {
  if (amount === null || amount === undefined || amount === "") return null;

  const numeric = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(numeric)) return null;

  return new Intl.NumberFormat("en-TZ", {
    style: "currency",
    currency,
    currencyDisplay: "code",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(numeric);
}
