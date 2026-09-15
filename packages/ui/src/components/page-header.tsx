import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export interface PageHeaderProps {
  eyebrow?: ReactNode;
  title: string;
  description?: string;
  actions?: ReactNode;
  /** "default" (most pages) or "large" — a bigger, denser command-center
   * style headline for a primary landing page (e.g. the tenant dashboard). */
  size?: "default" | "large";
  className?: string;
  /** Extra classes on the <h1> itself — e.g. a consumer-specific size/
   * line-height override. Merged after TITLE_SIZE, so an explicit
   * breakpoint here (sm:/lg:) wins over the size preset at that breakpoint. */
  titleClassName?: string;
  /** Extra classes on the description <p>, same merge behavior. */
  descriptionClassName?: string;
}

const TITLE_SIZE: Record<NonNullable<PageHeaderProps["size"]>, string> = {
  default: "text-2xl sm:text-3xl",
  large: "text-3xl sm:text-4xl lg:text-5xl leading-[1.05]",
};

/** Standard page title block: optional eyebrow row, title, description, right-aligned actions. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  size = "default",
  className,
  titleClassName,
  descriptionClassName,
}: PageHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between",
        className,
      )}
    >
      <div className="flex flex-col gap-1">
        {eyebrow && <div className="flex items-center gap-2">{eyebrow}</div>}
        <h1
          className={cn(
            "text-on-surface font-sans font-bold tracking-tight",
            TITLE_SIZE[size],
            titleClassName,
          )}
        >
          {title}
        </h1>
        {description && (
          <p className={cn("text-on-surface-variant text-sm", descriptionClassName)}>
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
