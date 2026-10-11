/**
 * Motion tokens — the ONLY place durations, easings and springs are defined.
 * Rules: animate transform/opacity only; 150–400 ms; progress visuals must be driven by
 * real backend events. Reduced motion is handled globally by <MotionConfig reducedMotion="user">
 * (transforms are skipped, opacity still fades) plus `fadeOnly` for anything custom.
 */
import type { Transition, Variants } from "motion/react";

export const duration = {
  instant: 0.12,
  fast: 0.18,
  base: 0.26,
  slow: 0.4,
  /** ambient loops (aurora drift, idle orb) — not interaction feedback */
  ambient: 18,
} as const;

export const ease = {
  /** default for enter/hover — quick out, soft landing */
  out: [0.22, 1, 0.36, 1],
  inOut: [0.65, 0, 0.35, 1],
  /** exits should get out of the way */
  in: [0.4, 0, 1, 1],
} as const satisfies Record<string, [number, number, number, number]>;

export const spring = {
  /** buttons, toggles, play/pause */
  snappy: { type: "spring", stiffness: 520, damping: 32, mass: 0.7 },
  /** cards, layout shifts */
  gentle: { type: "spring", stiffness: 260, damping: 28 },
  /** celebratory flourish */
  bouncy: { type: "spring", stiffness: 380, damping: 14 },
} as const satisfies Record<string, Transition>;

export const transition = {
  enter: { duration: duration.base, ease: ease.out },
  exit: { duration: duration.fast, ease: ease.in },
  hover: { duration: duration.fast, ease: ease.out },
} as const satisfies Record<string, Transition>;

/** Stagger for lists/grids of cards (library, file uploads). */
export const stagger = { children: 0.06, delay: 0.04 } as const;

export const variants = {
  fadeUp: {
    hidden: { opacity: 0, y: 12 },
    show: { opacity: 1, y: 0, transition: transition.enter },
    exit: { opacity: 0, y: -8, transition: transition.exit },
  },
  list: {
    hidden: {},
    show: { transition: { staggerChildren: stagger.children, delayChildren: stagger.delay } },
  },
  shake: {
    shake: { x: [0, -6, 6, -4, 4, 0], transition: { duration: duration.slow, ease: ease.inOut } },
  },
} as const satisfies Record<string, Variants>;

/** Use when you must hand-roll motion: collapse to a simple fade under reduced motion. */
export function fadeOnly(reduced: boolean | null, full: Variants): Variants {
  if (!reduced) return full;
  return {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { duration: duration.fast } },
    exit: { opacity: 0, transition: { duration: duration.fast } },
  };
}

/** Interaction presets for buttons. */
export const press = {
  whileHover: { scale: 1.03, transition: transition.hover },
  whileTap: { scale: 0.96, transition: spring.snappy },
} as const;
