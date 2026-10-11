import { motion, useReducedMotion } from "motion/react";
import { duration } from "../motion/tokens";

const blobs = [
  { color: "var(--aurora-1)", className: "-top-40 -left-32 size-[38rem]", drift: [0, 60, -20, 0] },
  { color: "var(--aurora-2)", className: "top-1/3 -right-40 size-[32rem]", drift: [0, -50, 30, 0] },
  { color: "var(--aurora-3)", className: "-bottom-48 left-1/4 size-[36rem]", drift: [0, 40, -40, 0] },
];

/** Slow ambient glow behind content. Transform-only; static under reduced motion. */
export function Aurora() {
  const reduced = useReducedMotion();
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {blobs.map((b, i) => (
        <motion.div
          key={i}
          className={`absolute rounded-full ${b.className}`}
          style={{ background: b.color, filter: `blur(var(--blur-aurora))`, willChange: "transform" }}
          animate={reduced ? undefined : { x: b.drift, y: b.drift.map((v) => -v * 0.6) }}
          transition={{ duration: duration.ambient + i * 4, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
      {/* faint grain-free vignette keeps edges calm */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,var(--color-bg)_100%)]" />
    </div>
  );
}
