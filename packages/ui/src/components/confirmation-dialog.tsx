"use client";

import { useEffect, useRef } from "react";
import { cn } from "../lib/cn";

export interface ConfirmationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
}

/** Lightweight, dependency-free modal for destructive/high-stakes confirmations. */
export function ConfirmationDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  onConfirm,
}: ConfirmationDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onOpenChange(false);
    }

    document.addEventListener("keydown", handleKeyDown);
    dialogRef.current?.focus();

    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={() => onOpenChange(false)}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirmation-dialog-title"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className="border-outline-variant/40 bg-surface-container-low w-full max-w-sm rounded-xl border p-6 shadow-2xl outline-none"
      >
        <h2 id="confirmation-dialog-title" className="text-on-surface text-lg font-semibold">
          {title}
        </h2>
        {description && <p className="text-on-surface-variant mt-2 text-sm">{description}</p>}

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={busy}
            className="text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={cn(
              "rounded-lg px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60",
              destructive
                ? "bg-danger/15 text-danger hover:bg-danger/25"
                : "bg-primary-container text-on-primary-container hover:brightness-110",
            )}
          >
            {busy ? "Please wait…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
