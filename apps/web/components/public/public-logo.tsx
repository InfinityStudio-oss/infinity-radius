import Image from "next/image";
import { cn } from "@infinity-radius/ui";

export interface PublicLogoProps {
  className?: string;
  /** "full" = shield + wordmark (header, footer brand column). "mark" =
   * shield only, for tight spaces. */
  variant?: "full" | "mark";
  priority?: boolean;
}

const FULL_ASPECT = 552 / 568;
const MARK_ASPECT = 413 / 464;

/**
 * Real Infinity Radius brand assets (apps/web/public/brand/), scoped to the
 * public marketing site only. The shared packages/ui Logo (invented SVG
 * mark) stays untouched — it's still used by the Tenant Dashboard and
 * Super Admin sidebars, which are out of scope for this redesign.
 */
export function PublicLogo({ className, variant = "full", priority }: PublicLogoProps) {
  if (variant === "mark") {
    return (
      <span className={cn("relative inline-block h-9 w-auto", className)} style={{ aspectRatio: MARK_ASPECT }}>
        <Image
          src="/brand/infinity-radius-mark.png"
          alt="Infinity Radius"
          fill
          priority={priority}
          className="object-contain"
          sizes="36px"
        />
      </span>
    );
  }

  return (
    <span className={cn("relative inline-block h-10 w-auto", className)} style={{ aspectRatio: FULL_ASPECT }}>
      <Image
        src="/brand/infinity-radius-logo-full.png"
        alt="Infinity Radius"
        fill
        priority={priority}
        className="object-contain"
        sizes="180px"
      />
    </span>
  );
}
