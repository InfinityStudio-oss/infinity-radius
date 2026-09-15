import { cn } from "../lib/cn";

export interface LogoMarkProps {
  className?: string;
}

/** The Infinity Radius brand mark: radiating signal arcs over an infinity core. */
export function LogoMark({ className }: LogoMarkProps) {
  return (
    <svg
      viewBox="0 0 48 48"
      width="32"
      height="32"
      fill="none"
      className={className}
      role="img"
      aria-label="Infinity Radius"
    >
      <defs>
        <linearGradient id="ir-logo-bg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#3B82F6" />
          <stop offset="50%" stopColor="#2563EB" />
          <stop offset="100%" stopColor="#4F46E5" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="44" height="44" rx="12" fill="url(#ir-logo-bg)" />
      <rect
        x="2"
        y="2"
        width="44"
        height="44"
        rx="12"
        stroke="#93C5FD"
        strokeWidth="1.5"
        strokeOpacity="0.3"
      />
      <path
        d="M14 17C19.5 12.5 28.5 12.5 34 17"
        stroke="#FFFFFF"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="M18 22C21.5 19 26.5 19 30 22"
        stroke="#E0E7FF"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="M18 30C16 30 14.5 28.5 14.5 26.5C14.5 24.5 16.5 23.5 19 25.5L29 32.5C31.5 34.5 33.5 33.5 33.5 31.5C33.5 29.5 32 28 30 28C28 28 26.5 29.5 26.5 31.5"
        stroke="#FFFFFF"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="24" cy="27" r="2.5" fill="#67E8F9" />
    </svg>
  );
}

export interface LogoProps {
  className?: string;
  markClassName?: string;
  wordmarkClassName?: string;
  /** A static product tagline under the wordmark (e.g. "Hotspot Operations")
   * — branding copy, never an operational/business value. Omit for the
   * plain single-line lockup. */
  subtitle?: string;
}

/** Full lockup: brand mark + "Infinity Radius" wordmark, optionally with a
 * product tagline underneath. */
export function Logo({ className, markClassName, wordmarkClassName, subtitle }: LogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark className={markClassName} />
      <span className="flex flex-col">
        <span
          className={cn(
            "text-on-surface font-sans text-lg font-bold leading-tight tracking-tight",
            wordmarkClassName,
          )}
        >
          Infinity Radius
        </span>
        {subtitle && (
          <span className="text-on-surface-variant font-mono text-[0.625rem] font-semibold uppercase leading-tight tracking-wider">
            {subtitle}
          </span>
        )}
      </span>
    </span>
  );
}
