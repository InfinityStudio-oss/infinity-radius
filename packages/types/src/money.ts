import type { CurrencyCode } from "./locale";

/**
 * Monetary amounts cross the wire as decimal strings (matching Postgres
 * NUMERIC and Python's Decimal) — never as JS `number` — so precision is
 * never lost to floating-point rounding. Formatting/arithmetic on the
 * frontend must go through a decimal-safe library (e.g. decimal.js),
 * never native `+`/`-`/`*` on parsed floats.
 */
export interface Money {
  amount: string;
  currency: CurrencyCode;
}
