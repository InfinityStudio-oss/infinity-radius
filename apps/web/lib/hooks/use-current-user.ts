"use client";

import { useApiQuery } from "@/lib/hooks/use-api-query";

export interface CurrentUser {
  id: string;
  email: string | null;
  full_name: string | null;
  tenant_id: string | null;
  tenant_name: string | null;
  roles: string[];
}

interface CurrentUserResponse {
  success: boolean;
  data: CurrentUser;
}

/**
 * The signed-in staff member's real identity, tenant, and roles —
 * database-resolved server-side (see app/api/v1/auth.py's GET /me), never
 * assumed from a JWT claim. Use this instead of hard-coding a tenant name
 * or role label anywhere in the dashboard shell.
 */
export function useCurrentUser() {
  return useApiQuery<CurrentUserResponse>("/api/v1/auth/me");
}
