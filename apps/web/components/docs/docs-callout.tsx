import { AlertTriangle, Info, StickyNote } from "lucide-react";
import { cn } from "@infinity-radius/ui";

export interface DocsCalloutProps {
  tone: "info" | "warning" | "note";
  children: React.ReactNode;
}

const TONE_STYLES = {
  info: {
    icon: Info,
    container: "border-blue-200 bg-blue-50 text-blue-900",
    icon_: "text-blue-600",
  },
  warning: {
    icon: AlertTriangle,
    container: "border-amber-200 bg-amber-50 text-amber-900",
    icon_: "text-amber-600",
  },
  note: {
    icon: StickyNote,
    container: "border-slate-200 bg-slate-50 text-slate-700",
    icon_: "text-slate-500",
  },
} as const;

export function DocsCallout({ tone, children }: DocsCalloutProps) {
  const style = TONE_STYLES[tone];
  const Icon = style.icon;

  return (
    <div className={cn("flex items-start gap-3 rounded-lg border px-4 py-3 text-sm leading-relaxed", style.container)}>
      <Icon size={17} className={cn("mt-0.5 shrink-0", style.icon_)} />
      <div>{children}</div>
    </div>
  );
}
