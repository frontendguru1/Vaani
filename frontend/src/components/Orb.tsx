import { motion, useReducedMotion } from "motion/react";
import { spring } from "../motion/tokens";

interface Props {
  hue: number;
  /** 0..1 real progress from the backend, or null when idle */
  progress: number | null;
  active: boolean;
  done?: boolean;
  size?: number;
  label?: string;
}

/**
 * The generation orb: a soft sphere in the voice's colour that breathes while the model
 * works. Its outer ring is the real progress (driven by backend events, never faked).
 */
export function Orb({ hue, progress, active, done = false, size = 200, label }: Props) {
  const reduced = useReducedMotion();
  const r = size / 2 - 6;
  const c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(1, progress ?? 0));
  const core = `oklch(0.72 0.17 ${hue})`;
  const edge = `oklch(0.6 0.16 ${(hue + 45) % 360})`;

  return (
    <div className="relative mx-auto" style={{ width: size, height: size }} role="img" aria-label={label}>
      {/* glow */}
      <motion.div
        aria-hidden
        className="absolute inset-[14%] rounded-full"
        style={{ background: core, filter: "blur(36px)", opacity: 0.35 }}
        animate={active && !reduced ? { scale: [1, 1.18, 1], opacity: [0.3, 0.55, 0.3] } : { scale: 1, opacity: done ? 0.5 : 0.25 }}
        transition={active ? { duration: 2.4, repeat: Infinity, ease: "easeInOut" } : spring.gentle}
      />
      {/* sphere */}
      <motion.div
        aria-hidden
        className="absolute inset-[22%] rounded-full"
        style={{
          background: `radial-gradient(circle at 35% 30%, oklch(0.92 0.06 ${hue}) 0%, ${core} 38%, ${edge} 75%, oklch(0.3 0.08 ${hue}) 100%)`,
          boxShadow: `inset 0 -10px 30px oklch(0.25 0.08 ${hue} / .6), 0 0 40px oklch(0.72 0.17 ${hue} / .35)`,
        }}
        animate={
          reduced
            ? {}
            : active
              ? { scale: [1, 1.06, 0.98, 1.04, 1], rotate: [0, 6, -4, 0] }
              : done
                ? { scale: [1, 1.12, 1] }
                : { scale: [1, 1.015, 1] }
        }
        transition={
          active
            ? { duration: 2.4, repeat: Infinity, ease: "easeInOut" }
            : done
              ? spring.bouncy
              : { duration: 6, repeat: Infinity, ease: "easeInOut" }
        }
      />
      {/* progress ring */}
      <svg className="absolute inset-0 -rotate-90" viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgb(255 255 255 / .07)" strokeWidth="3" />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={core}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={c}
          initial={false}
          animate={{ strokeDashoffset: c * (1 - p), opacity: progress == null ? 0 : 1 }}
          transition={spring.gentle}
          style={{ filter: `drop-shadow(0 0 6px ${core})` }}
        />
      </svg>
    </div>
  );
}
