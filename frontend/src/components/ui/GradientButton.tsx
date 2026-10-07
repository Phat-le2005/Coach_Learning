import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

import styles from "./ui.module.css";

type ButtonVisualVariant = "primary" | "secondary" | "ghost";

interface SharedProps {
  children: ReactNode;
  className?: string;
  variant?: ButtonVisualVariant;
}

type LinkProps = SharedProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "className" | "children"> & {
    href: string;
  };

type NativeButtonProps = SharedProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className" | "children"> & {
    href?: never;
  };

export type GradientButtonProps = LinkProps | NativeButtonProps;

const variantClass: Record<ButtonVisualVariant, string> = {
  primary: styles.buttonPrimary,
  secondary: styles.buttonSecondary,
  ghost: styles.buttonGhost,
};

export function GradientButton(props: GradientButtonProps) {
  const { children, className, variant = "primary" } = props;
  const classes = [styles.button, variantClass[variant], className ?? ""].filter(Boolean).join(" ");

  if ("href" in props && typeof props.href === "string") {
    const { href, children: linkChildren, className: _className, variant: _variant, ...anchorProps } = props;
    return (
      <a className={classes} href={href} {...anchorProps}>
        {linkChildren}
      </a>
    );
  }

  const { children: buttonChildren, className: _className, variant: _variant, ...buttonProps } = props;
  return (
    <button className={classes} type="button" {...buttonProps}>
      {buttonChildren}
    </button>
  );
}
