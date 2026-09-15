# Localization

Initial target market: **Tanzania**. Every value below is a default, not a
hard-coded assumption — the schema/config keeps room for additional
countries/currencies later, but nothing beyond Tanzania is implemented yet.

| Setting      | Value                            | Defined in                                                    |
| ------------ | -------------------------------- | ------------------------------------------------------------- |
| Country      | Tanzania (`TZ`)                  | `packages/types/src/locale.ts`, `apps/api/app/core/config.py` |
| Currency     | TZS                              | same                                                          |
| Timezone     | `Africa/Dar_es_Salaam`           | same                                                          |
| Locale       | `en-TZ`                          | same                                                          |
| Phone format | `+255XXXXXXXXX` / `255XXXXXXXXX` | `TZ_PHONE_REGEX` in `packages/types/src/locale.ts`            |

## Money

- Never `float`/JS `number` for currency amounts.
- Postgres: `NUMERIC`.
- Python: `decimal.Decimal`.
- Wire format (API <-> frontend): a decimal string, e.g. `{"amount": "15000.00", "currency": "TZS"}` — see `packages/types/src/money.ts`.
- Frontend arithmetic/formatting must go through a decimal-safe library, never native `+`/`-`/`*` on parsed floats.

## Adding a second country later

1. Add the new currency/locale/timezone as additional supported values
   (not a replacement) in `packages/types/src/locale.ts` and
   `apps/api/app/core/config.py`.
2. Make currency/timezone/locale per-tenant fields (already modeled that
   way on `Tenant` in `packages/types/src/auth.ts`) rather than
   process-wide constants.
3. Extend `TZ_PHONE_REGEX`-style validation per supported country.
