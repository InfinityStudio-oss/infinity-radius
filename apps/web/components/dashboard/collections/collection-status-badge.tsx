"use client";

import { StatusBadge } from "@infinity-radius/ui";
import { presentCollectionStatus } from "@/lib/collections/status";

export interface CollectionStatusBadgeProps {
  status: string | null | undefined;
  pulse?: boolean;
}

/**
 * Renders any Collection status — including one this build doesn't know —
 * without ever falling back to something that reads as success.
 */
export function CollectionStatusBadge({ status, pulse }: CollectionStatusBadgeProps) {
  const presentation = presentCollectionStatus(status);
  return (
    <StatusBadge
      variant={presentation.variant}
      label={presentation.label}
      pulse={pulse ?? presentation.isPolling}
    />
  );
}
