import { cn } from "../lib/cn";
import { formatMoney } from "../lib/money";

export interface MoneyDisplayProps {
  /** Decimal string (e.g. "15000.00"), matching packages/types Money.amount. Never a pre-rounded float. */
  amount: string | null | undefined;
  currency?: string;
  className?: string;
}

/**
 * Renders a decimal-string amount as localized currency, TZS by default.
 * The string -> Number conversion here is for DISPLAY ONLY; no arithmetic is
 * ever performed on the result — real money math stays server-side as
 * Decimal/NUMERIC. Renders an em dash when no amount is available, never 0.
 */
export function MoneyDisplay({ amount, currency = "TZS", className }: MoneyDisplayProps) {
  const formatted = formatMoney(amount, currency);

  if (formatted === null) {
    return <span className={cn("text-on-surface-variant font-mono", className)}>—</span>;
  }

  return <span className={cn("font-mono", className)}>{formatted}</span>;
}
