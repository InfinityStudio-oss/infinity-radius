"use client";

import type { ReactNode } from "react";
import {
  DataTable,
  ErrorState,
  PageHeader,
  SearchInput,
  type DataTableColumn,
} from "@infinity-radius/ui";
import { useApiQuery } from "@/lib/hooks/use-api-query";
import type { ResourceListResponse } from "@/lib/api-types";

type Row = { id: string | number } & Record<string, unknown>;

export interface ResourceListPageProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  eyebrow?: ReactNode;
  /** API path, e.g. "/api/v1/tenant/resources/customers". */
  resourcePath: string;
  columns: DataTableColumn<Row>[];
  emptyIcon?: ReactNode;
  emptyTitle: string;
  emptyDescription?: string;
  searchPlaceholder?: string;
}

/**
 * Standard list-page shell: PageHeader + search + a DataTable wired to a
 * real backend resource endpoint, covering Loading/Error/Empty/Success
 * without the page itself branching on network state.
 */
export function ResourceListPage({
  title,
  description,
  actions,
  eyebrow,
  resourcePath,
  columns,
  emptyIcon,
  emptyTitle,
  emptyDescription,
  searchPlaceholder,
}: ResourceListPageProps) {
  const { state, data, error, refetch } = useApiQuery<ResourceListResponse>(resourcePath);

  if (state === "error") {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={title} description={description} actions={actions} eyebrow={eyebrow} />
        <ErrorState title="Unable to load data" description={error?.message} onRetry={refetch} />
      </div>
    );
  }

  const rows = (data?.items ?? []) as Row[];
  const tableState = state === "loading" ? "loading" : rows.length === 0 ? "empty" : "success";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={title} description={description} actions={actions} eyebrow={eyebrow} />

      {searchPlaceholder && (
        <SearchInput placeholder={searchPlaceholder} disabled containerClassName="max-w-sm" />
      )}

      <DataTable
        columns={columns}
        rows={rows}
        state={tableState}
        emptyState={{ icon: emptyIcon, title: emptyTitle, description: emptyDescription }}
      />
    </div>
  );
}
