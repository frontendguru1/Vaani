import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { useEffect } from "react";
import type { Rating } from "../lib/api";
import { duration, ease } from "../motion/tokens";

const ratingColor: Record<Rating, string> = {
  good: "var(--color-good)",
  okay: "var(--color-okay)",
  poor: "var(--color-poor)",
};
export const ratingLabel: Record<Rating, string> = { good: "Good", okay: "Okay", poor: "Poor" };

/** Animated quality score: the number counts up and the ring fills, colour by rating. */
export function ScoreRing({ score, rating, size = 64 }: { score: number; rating: Rating; size?: number }) {
  const reduced = useReducedMotion();
  const value = useMotionValue(0);
  const text = useTransform(value, (v) => String(Math.round(v)));
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  const offset = useTransform(value, (v) => c * (1 - v / 100));

  useEffect(() => {
    const ctrl = animate(value, score, { duration: reduced ? 0 : 0.9, ease: ease.out });
    return () => ctrl.stop();
  }, [score, reduced, value]);

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(255 255 255 / .08)" strokeWidth="4" />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={c}
          style={{ strokeDashoffset: offset }}
          animate={{ stroke: ratingColor[rating] }}
          transition={{ duration: duration.slow }}
        />
      </svg>
      <motion.span
        className="absolute inset-0 flex items-center justify-center font-mono text-sm font-medium"
        animate={{ color: ratingColor[rating] }}
        aria-label={`Quality ${ratingLabel[rating]}, score ${score} of 100`}
      >
        {text}
      </motion.span>
    </div>
  );
}

export function RatingPill({ rating }: { rating: Rating }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{ color: ratingColor[rating], background: `color-mix(in oklch, ${ratingColor[rating]} 14%, transparent)` }}
    >
      <span className="size-1.5 rounded-full" style={{ background: ratingColor[rating] }} />
      {ratingLabel[rating]}
    </span>
  );
}
