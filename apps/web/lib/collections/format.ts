/**
 * Display helpers for Collection views. Africa/Dar_es_Salaam matches the
 * timezone every other dashboard panel already renders in (see
 * components/dashboard/recent-transactions-table.tsx and friends).
 */

const TIME_ZONE = "Africa/Dar_es_Salaam";

/** Date + time, e.g. "20 Sep 2026, 07:49". Returns an em dash for null. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString("en-GB", {
    timeZone: TIME_ZONE,
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Compact form for table cells, e.g. "20 Sep, 07:49". */
export function formatDateTimeShort(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleString("en-GB", {
    timeZone: TIME_ZONE,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Renders an em dash rather than an empty cell for absent values. */
export function orDash(value: string | null | undefined): string {
  return value && value.trim() !== "" ? value : "—";
}
