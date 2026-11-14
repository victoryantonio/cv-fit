import { clsx } from "clsx";
import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

/**
 * Every variant keeps the same height, so a button whose label becomes
 * "Saving…" does not make the row jump.
 */
const VARIANTS: Record<Variant, string> = {
  primary: "border border-accent bg-accent text-onaccent hover:bg-accent-hover",
  secondary: "border border-line bg-bg text-ink hover:bg-panel",
  ghost: "border border-transparent text-muted hover:bg-panel hover:text-ink",
  danger: "border border-gap-line bg-gap-bg text-gap-fg hover:border-gap-fg",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  busy?: boolean;
};

/**
 * The ref is forwarded because `asChild` triggers (Radix Dialog) need it to
 * move focus; a plain function component would silently drop it.
 */
export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = "secondary", busy = false, className, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      {...rest}
      aria-busy={busy || undefined}
      disabled={rest.disabled || busy}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-dense transition-colors duration-fast disabled:cursor-not-allowed disabled:opacity-60",
        VARIANTS[variant],
        className,
      )}
    />
  );
});
