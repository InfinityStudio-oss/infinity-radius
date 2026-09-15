"use client";

import { useState } from "react";
import { SearchInput } from "@infinity-radius/ui";

/**
 * A real, typeable, controlled search field — the UI boundary is wired up
 * (customer phone/name, username, voucher, transaction reference, router
 * name, MAC address are the real identifiers this is meant to cover), but
 * there is no cross-entity global search endpoint on the backend yet.
 * Rather than fabricate suggestions or silently point this at one
 * entity's list endpoint and call that "search", submitting is a no-op
 * for now — a real handler slots in here the moment
 * GET /api/v1/search (or similar) exists.
 */
export function TopBarSearch({ containerClassName = "w-56 xl:w-80 2xl:w-96" }: { containerClassName?: string }) {
  const [value, setValue] = useState("");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        // No global search endpoint exists yet — intentionally a no-op
        // rather than a fabricated result set. See this file's docstring.
      }}
    >
      <SearchInput
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Search IP, MAC, voucher code, subscriber…"
        containerClassName={containerClassName}
      />
    </form>
  );
}
