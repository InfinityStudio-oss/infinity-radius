/**
 * Localization constants. Tanzania is the initial target market; this module
 * is the single place that will need to change to support additional
 * countries/currencies later.
 */
export const DEFAULT_COUNTRY = "Tanzania" as const;
export const DEFAULT_COUNTRY_CODE = "TZ" as const;
export const DEFAULT_CURRENCY = "TZS" as const;
export const DEFAULT_TIMEZONE = "Africa/Dar_es_Salaam" as const;
export const DEFAULT_LOCALE = "en-TZ" as const;
export const DEFAULT_PHONE_COUNTRY_CALLING_CODE = "+255" as const;

/** Matches +255XXXXXXXXX or 255XXXXXXXXX (Tanzanian MSISDN, 9 digits after the country code). */
export const TZ_PHONE_REGEX = /^(\+?255)(6|7)\d{8}$/;

export type CurrencyCode = "TZS";
