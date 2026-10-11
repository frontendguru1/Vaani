import { motion } from "motion/react";
import { spring } from "../motion/tokens";

export function ProgressRing({ value, size = 28, color = "var(--color-violet-soft)" }: { value: number; size?: number; color?: string }) {
  const r = size / 2 - 2.5;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" role="progressbar"
      aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(255 255 255 / .1)" strokeWidth="2.5" />
      <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="2.5"
        strokeLinecap="round" strokeDasharray={c} initial={{ strokeDashoffset: c }}
        animate={{ strokeDashoffset: c * (1 - value) }} transition={spring.gentle} />
    </svg>
  );
}
