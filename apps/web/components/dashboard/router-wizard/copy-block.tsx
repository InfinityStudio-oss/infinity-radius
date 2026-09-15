"use client";

import { useState } from "react";
import { Check, Copy, Download } from "lucide-react";

export interface CopyBlockProps {
  label: string;
  code: string;
  filename?: string;
  /** Shown once, right above the code — for the one moment a generated
   * secret (WireGuard private key, RADIUS secret) is visible. Never
   * persisted anywhere after this render — not localStorage, not a query
   * param, not a log line. */
  warning?: string;
}

/**
 * Copyable + downloadable config text block used throughout the Add Router
 * Wizard. Download builds the file client-side from the value already in
 * memory (a Blob object URL) — nothing is re-fetched from, or re-sent to,
 * the backend to produce it, so a secret shown here never makes a second
 * round trip.
 */
export function CopyBlock({ label, code, filename, warning }: CopyBlockProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API can be unavailable (insecure context, permissions) —
      // the text is still fully visible/selectable below, so this is a
      // convenience failure, not a blocker.
    }
  }

  function handleDownload() {
    const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename ?? "router-config.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="bg-surface-container-low flex flex-col gap-2 rounded-lg p-3">
      <div className="flex items-center justify-between">
        <span className="text-on-surface-variant text-xs font-semibold uppercase tracking-wide">
          {label}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleCopy}
            className="text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? "Copied" : "Copy"}
          </button>
          {filename && (
            <button
              type="button"
              onClick={handleDownload}
              className="text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors"
            >
              <Download size={14} />
              Download
            </button>
          )}
        </div>
      </div>
      {warning && (
        <p className="text-error text-xs font-medium">{warning}</p>
      )}
      <pre className="bg-surface-container-lowest text-on-surface max-h-64 overflow-auto rounded-md p-3 font-mono text-xs leading-relaxed">
        {code}
      </pre>
    </div>
  );
}
