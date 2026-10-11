import { motion, useReducedMotion } from "motion/react";
import { useMemo } from "react";
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

const RAYS = 48;
const ORBITS = [
  { r: 0.44, tilt: 62, dur: 5.5, dots: 3, delay: 0 },
  { r: 0.4, tilt: -48, dur: 7.5, dots: 2, delay: 0.8 },
  { r: 0.47, tilt: 18, dur: 9.5, dots: 4, delay: 1.6 },
];

/**
 * The generation orb, in the voice's own colour.
 * Idle: a calm sphere that barely breathes.
 * Working: a rotating colour halo, "thought" blobs drifting inside the sphere, particles on
 * tilted orbits and a ring of sound rays pulsing outward — the model is thinking.
 * The outer ring is always the REAL progress from the backend (never faked).
 */
export function Orb({ hue, progress, active, done = false, size = 200, label }: Props) {
  const reduced = useReducedMotion();
  const animate = active && !reduced;
  const r = size / 2 - 6;
  const c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(1, progress ?? 0));
  const core = `oklch(0.72 0.17 ${hue})`;
  const edge = `oklch(0.6 0.16 ${(hue + 45) % 360})`;
  const accent = `oklch(0.8 0.15 ${(hue + 70) % 360})`;
  const deep = `oklch(0.3 0.08 ${hue})`;
  const rays = useMemo(() => Array.from({ length: RAYS }, (_, i) => (i / RAYS) * 360), []);

  return (
    <div className="relative mx-auto" style={{ width: size, height: size }} role="img" aria-label={label}>
      {/* soft glow */}
      <motion.div
        aria-hidden
        className="absolute inset-[12%] rounded-full"
        style={{ background: core, filter: "blur(38px)" }}
        animate={animate ? { scale: [1, 1.2, 1], opacity: [0.35, 0.6, 0.35] } : { scale: 1, opacity: done ? 0.5 : 0.25 }}
        transition={animate ? { duration: 2.4, repeat: Infinity, ease: "easeInOut" } : spring.gentle}
      />

      {/* rotating colour halo (conic), only while working */}
      <motion.div
        aria-hidden
        className="absolute inset-[15%] rounded-full"
        style={{
          background: `conic-gradient(from 0deg, transparent 0deg, ${core} 70deg, transparent 140deg, ${accent} 220deg, transparent 300deg)`,
          filter: "blur(10px)",
          WebkitMask: "radial-gradient(circle, transparent 58%, #000 60%, #000 70%, transparent 72%)",
          mask: "radial-gradient(circle, transparent 58%, #000 60%, #000 70%, transparent 72%)",
        }}
        initial={false}
        animate={animate ? { rotate: 360, opacity: 0.9 } : { rotate: 0, opacity: 0 }}
        transition={animate ? { rotate: { duration: 3.2, repeat: Infinity, ease: "linear" }, opacity: { duration: 0.4 } } : { duration: 0.4 }}
      />

      {/* sound rays pulsing outward in a travelling wave */}
      <svg aria-hidden className="absolute inset-0" viewBox="0 0 100 100">
        {rays.map((deg, i) => (
          // Rotate a plain <g> with an SVG transform: motion's own rotate would spin each
          // line around its own box (transform-box: fill-box) and stack them all at the top.
          <g key={i} transform={`rotate(${deg} 50 50)`}>
            <motion.line
              x1="50"
              y1="21"
              x2="50"
              y2="18.5"
              stroke={i % 2 ? core : accent}
              strokeWidth="0.8"
              strokeLinecap="round"
              initial={false}
              animate={animate ? { y2: [18.5, 13, 18.5], opacity: [0.15, 0.9, 0.15] } : { y2: 18.5, opacity: 0 }}
              transition={
                animate
                  ? { duration: 1.4, repeat: Infinity, ease: "easeInOut", delay: (i / RAYS) * 1.4 }
                  : { duration: 0.3 }
              }
            />
          </g>
        ))}
      </svg>

      {/* sphere */}
      <motion.div
        aria-hidden
        className="absolute inset-[24%] overflow-hidden rounded-full"
        style={{
          background: `radial-gradient(circle at 35% 30%, oklch(0.92 0.06 ${hue}) 0%, ${core} 38%, ${edge} 75%, ${deep} 100%)`,
          boxShadow: `inset 0 -10px 30px oklch(0.25 0.08 ${hue} / .6), 0 0 40px oklch(0.72 0.17 ${hue} / .35)`,
        }}
        animate={
          reduced
            ? {}
            : active
              ? { scale: [1, 1.05, 0.98, 1.04, 1] }
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
      >
        {/* "thought" blobs drifting inside the sphere */}
        {[
          { color: accent, x: [-18, 22, -10, -18], y: [-12, 8, 20, -12], d: 4.2 },
          { color: `oklch(0.95 0.05 ${hue})`, x: [16, -14, 10, 16], y: [14, -10, -18, 14], d: 5.6 },
          { color: edge, x: [0, 18, -20, 0], y: [20, -16, 4, 20], d: 6.8 },
        ].map((b, i) => (
          <motion.span
            key={i}
            className="absolute top-1/2 left-1/2 size-[55%] -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ background: b.color, filter: "blur(14px)", mixBlendMode: "screen" }}
            initial={false}
            animate={animate ? { x: b.x.map((v) => `${v}%`), y: b.y.map((v) => `${v}%`), opacity: 0.55 } : { x: "0%", y: "0%", opacity: 0 }}
            transition={animate ? { duration: b.d, repeat: Infinity, ease: "easeInOut" } : { duration: 0.5 }}
          />
        ))}
        {/* specular highlight stays on top so it still reads as a sphere */}
        <span className="absolute top-[12%] left-[18%] h-[28%] w-[34%] rounded-full bg-white/35 blur-[6px]" />
      </motion.div>

      {/* particles on tilted orbits */}
      {ORBITS.map((o, oi) => (
        <div
          key={oi}
          aria-hidden
          className="absolute inset-0"
          style={{ transform: `rotateX(70deg) rotateZ(${o.tilt}deg)`, transformStyle: "preserve-3d", perspective: 600 }}
        >
          <motion.div
            className="absolute inset-0"
            initial={false}
            animate={animate ? { rotate: 360, opacity: 1 } : { rotate: 0, opacity: 0 }}
            transition={animate ? { rotate: { duration: o.dur, repeat: Infinity, ease: "linear", delay: o.delay }, opacity: { duration: 0.4 } } : { duration: 0.4 }}
          >
            {Array.from({ length: o.dots }, (_, di) => {
              const a = (di / o.dots) * Math.PI * 2;
              const rad = o.r * size;
              return (
                <span
                  key={di}
                  className="absolute size-1.5 rounded-full"
                  style={{
                    left: size / 2 + Math.cos(a) * rad - 3,
                    top: size / 2 + Math.sin(a) * rad - 3,
                    background: di % 2 ? accent : "white",
                    boxShadow: `0 0 8px ${core}, 0 0 14px ${core}`,
                  }}
                />
              );
            })}
          </motion.div>
        </div>
      ))}

      {/* real progress ring */}
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
