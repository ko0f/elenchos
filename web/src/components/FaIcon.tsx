import type { HTMLAttributes } from "react";

export type FaIconStyle = "solid" | "regular" | "brands";

const STYLE_CLASS: Record<FaIconStyle, string> = {
  solid: "fa-solid",
  regular: "fa-regular",
  brands: "fa-brands",
};

export type FaIconProps = Omit<HTMLAttributes<HTMLElement>, "children"> & {
  /** Icon name without the `fa-` prefix (e.g. `gauge`, `trophy`). */
  icon: string;
  variant?: FaIconStyle;
};

/** Font Awesome icon (`<i class="fa-solid fa-…">`). Requires `fontawesome/css/all.min.css`. */
export function FaIcon({
  icon,
  variant = "solid",
  className,
  ...rest
}: FaIconProps) {
  const classes = [STYLE_CLASS[variant], `fa-${icon}`, className]
    .filter(Boolean)
    .join(" ");
  return <i className={classes} aria-hidden {...rest} />;
}
