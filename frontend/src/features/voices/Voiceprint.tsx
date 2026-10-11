import { motion, useReducedMotion } from "motion/react";
import { useMemo } from "react";
import { spring } from "../../motion/tokens";

/**
 * A radial "voiceprint": bars around a circle that grow from noise into a settled shape as
 * the voice is processed (progress is real), then pulse once when it's ready.
 */
export function Voiceprint({ hue, progress, ready, seed = "vaani" }: { hue: number; progress: number; ready: boolean; seed?: string }) {
  const reduced = useReducedMotion();
  const N = 56;
  const shape = useMemo(() => {
    let h = 0;
    for (const ch of seed) h = (h * 33 + ch.charCodeAt(0)) >>> 0;
    return Array.from({ length: N }, (_, i) => {
      const a = (i / N) * Math.PI * 2;
      return 0.45 + 0.3 * Math.abs(Math.sin(a * 3 + (h % 7))) + 0.25 * Math.abs(Math.sin(a * 7 + (h % 5)));
    });
  }, [seed]);

  const size = 180;
  const c = size / 2;
  const inner = 34;
  const maxLen = 48;
  const color = `oklch(0.75 0.16 ${hue})`;
  const color2 = `oklch(0.75 0.14 ${(hue + 60) % 360})`;

  return (
    <motion.svg
      viewBox={`0 0 ${size} ${size}`}
      className="mx-auto block size-44"
      animate={ready && !reduced ? { scale: [1, 1.08, 1] } : { scale: 1 }}
      transition={spring.bouncy}
      role="img"
      aria-label={ready ? "Voiceprint ready" : "Building voiceprint"}
    >
      <defs>
        <linearGradient id="vp-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={color} />
          <stop offset="1" stopColor={color2} />
        </linearGradient>
      </defs>
      <circle cx={c} cy={c} r={inner - 8} fill={`oklch(0.72 0.17 ${hue} / ${0.1 + progress * 0.25})`} />
      {shape.map((s, i) => {
        const a = (i / N) * Math.PI * 2 - Math.PI / 2;
        // Before settling, bars jitter; they converge on the voice's shape as progress grows.
        const len = maxLen * (ready ? s : s * (0.15 + 0.85 * progress));
        return (
          <motion.line
            key={i}
            x1={c + Math.cos(a) * inner}
            y1={c + Math.sin(a) * inner}
            stroke="url(#vp-grad)"
            strokeWidth={3}
            strokeLinecap="round"
            initial={false}
            animate={{
              x2: c + Math.cos(a) * (inner + len),
              y2: c + Math.sin(a) * (inner + len),
              opacity: 0.35 + 0.65 * (ready ? 1 : progress),
            }}
            transition={{ ...spring.gentle, delay: reduced ? 0 : (i % 8) * 0.01 }}
          />
        );
      })}
    </motion.svg>
  );
}

/** Short celebratory burst when a voice is ready. */
export function Flourish({ hue }: { hue: number }) {
  const reduced = useReducedMotion();
  if (reduced) return null;
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center">
      {Array.from({ length: 14 }, (_, i) => {
        const a = (i / 14) * Math.PI * 2;
        return (
          <motion.span
            key={i}
            className="absolute size-2 rounded-full"
            style={{ background: `oklch(0.8 0.16 ${(hue + i * 12) % 360})` }}
            initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
            animate={{ x: Math.cos(a) * 130, y: Math.sin(a) * 130, opacity: 0, scale: 0.3 }}
            transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          />
        );
      })}
    </div>
  );
}
