import { motion, type HTMLMotionProps } from "motion/react";
import { forwardRef } from "react";
import { press } from "../motion/tokens";

type Variant = "primary" | "ghost" | "danger" | "quiet";

const styles: Record<Variant, string> = {
  primary: "btn-primary text-white disabled:opacity-50",
  ghost: "border border-line bg-glass text-ink hover:bg-white/[0.08] disabled:opacity-50",
  danger: "border border-poor/40 bg-poor/10 text-poor hover:bg-poor/20 disabled:opacity-50",
  quiet: "text-muted hover:text-ink hover:bg-white/[0.06] disabled:opacity-40",
};

interface Props extends HTMLMotionProps<"button"> {
  variant?: Variant;
  size?: "sm" | "md" | "lg";
}

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = "ghost", size = "md", className = "", disabled, ...rest },
  ref,
) {
  const sizes = { sm: "h-8 px-3 text-xs gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-12 px-6 text-[15px] gap-2" };
  return (
    <motion.button
      ref={ref}
      type="button"
      disabled={disabled}
      {...(disabled ? {} : press)}
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-medium transition-colors disabled:cursor-not-allowed ${sizes[size]} ${styles[variant]} ${className}`}
      {...rest}
    />
  );
});
