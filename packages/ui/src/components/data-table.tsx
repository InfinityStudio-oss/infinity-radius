import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import { EmptyState, type EmptyStateProps } from "./empty-state";
import { ErrorState, type ErrorStateProps } from "./error-state";
import { LoadingSkeletonRow } from "./loading-skeleton";

export type DataTableState = "loading" | "error" | "empty" | "success";

export interface DataTableColumn<T> {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  render?: (row: T) => ReactNode;
}

export interface DataTableProps<T extends { id: string | number }> {
  columns: DataTableColumn<T>[];
  rows: T[];
  state: DataTableState;
  skeletonRows?: number;
  emptyState: Omit<EmptyStateProps, "className">;
  errorState?: Omit<ErrorStateProps, "className">;
  className?: string;
}

const ALIGN_CLASS = { left: "text-left", right: "text-right", center: "text-center" } as const;

/**
 * Table shell that owns its own loading/error/empty/success rendering so
 * every list page gets all four states for free from one `state` prop —
 * never substitute an empty response with placeholder rows.
 */
export function DataTable<T extends { id: string | number }>({
  columns,
  rows,
  state,
  skeletonRows = 5,
  emptyState,
  errorState,
  className,
}: DataTableProps<T>) {
  if (state === "empty") {
    return <EmptyState {...emptyState} className={className} />;
  }

  if (state === "error") {
    return <ErrorState title="Unable to load data" {...errorState} className={className} />;
  }

  return (
    <div className={cn("bg-surface-container-low w-full overflow-x-auto rounded-xl", className)}>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-surface-container-high text-on-surface-variant border-b font-sans text-[0.6875rem] font-semibold uppercase tracking-wider">
            {columns.map((col) => (
              <th key={col.key} className={cn("px-3 py-2.5", col.align && ALIGN_CLASS[col.align])}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-surface-container/60 divide-y">
          {state === "loading"
            ? Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={i}>
                  <td colSpan={columns.length}>
                    <LoadingSkeletonRow columns={columns.length} />
                  </td>
                </tr>
              ))
            : rows.map((row) => (
                <tr key={row.id} className="hover:bg-surface-container/60 transition-colors">
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn("px-3 py-2.5", col.align && ALIGN_CLASS[col.align])}
                    >
                      {col.render
                        ? col.render(row)
                        : String((row as Record<string, unknown>)[col.key] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
