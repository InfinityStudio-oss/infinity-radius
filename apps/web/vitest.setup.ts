import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// The client env module reads NEXT_PUBLIC_* at import time; tests never
// talk to a real backend, so a placeholder base URL is enough and makes it
// obvious in any accidental network attempt that it came from a test.
process.env.NEXT_PUBLIC_API_BASE_URL ??= "http://api.test.invalid";
process.env.NEXT_PUBLIC_SUPABASE_URL ??= "http://supabase.test.invalid";
process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ??= "test-anon-key-not-a-real-credential";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
