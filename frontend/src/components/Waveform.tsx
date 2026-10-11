import { motion, useReducedMotion } from "motion/react";
import { useEffect, useId, useRef, useState } from "react";
import { duration, ease } from "../motion/tokens";
import { peaksFor } from "./peaks";

interface Props {
  source: string | Blob | null;
  sourceKey?: string;
  /** Fixed bar count; by default one bar per ~6px of measured width. */
  bars?: number;
  height?: number;
  color?: string;
  progress?: number; // 0..1, the played portion is drawn brighter
  onSeek?: (fraction: number) => void;
  label?: string;
}

/** SVG bar waveform that draws itself in once decoded, with a played-portion overlay. */
export function Waveform({
  source,
  sourceKey,
  bars: fixedBars,
  height = 56,
  color = "var(--color-violet-soft)",
  progress = 0,
  onSeek,
  label = "Waveform",
}: Props) {
  const [peaks, setPeaks] = useState<number[] | null>(null);
  const [failed, setFailed] = useState(false);
  const reduced = useReducedMotion();
  const id = useId().replace(/:/g, "");
  const box = useRef<HTMLDivElement>(null);
  const [autoBars, setAutoBars] = useState(0);
  const bars = fixedBars ?? autoBars;

  useEffect(() => {
    if (fixedBars || !box.current) return;
    const el = box.current;
    const measure = () => {
      // Snap to steps of 8 so tiny resizes don't re-decode the audio.
      const n = Math.max(24, Math.min(240, Math.floor(el.clientWidth / 6 / 8) * 8));
      setAutoBars((b) => (b === n ? b : n));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [fixedBars]);

  useEffect(() => {
    let alive = true;
    setPeaks(null);
    setFailed(false);
    if (!source || !bars) return;
    peaksFor(source, bars, sourceKey)
      .then((p) => alive && setPeaks(p))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [source, sourceKey, bars]);

  const gap = 2;
  const width = bars * 6;
  const barW = width / bars - gap;

  const seek = (e: React.MouseEvent<SVGSVGElement> | React.KeyboardEvent<SVGSVGElement>) => {
    if (!onSeek) return;
    if ("key" in e) {
      if (e.key === "ArrowRight") onSeek(Math.min(1, progress + 0.05));
      if (e.key === "ArrowLeft") onSeek(Math.max(0, progress - 0.05));
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)));
  };

  if (!peaks || peaks.length !== bars) {
    return (
      <div
        ref={box}
        className={`w-full rounded-md ${failed ? "" : "animate-pulse"} bg-white/[0.04]`}
        style={{ height }}
        aria-label={failed ? "Waveform unavailable" : "Loading waveform"}
      />
    );
  }

  return (
    <div ref={box} className="w-full">
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={`block w-full ${onSeek ? "cursor-pointer" : ""}`}
      style={{ height }}
      role={onSeek ? "slider" : "img"}
      aria-label={label}
      aria-valuenow={onSeek ? Math.round(progress * 100) : undefined}
      aria-valuemin={onSeek ? 0 : undefined}
      aria-valuemax={onSeek ? 100 : undefined}
      tabIndex={onSeek ? 0 : undefined}
      onClick={seek}
      onKeyDown={seek}
    >
      <defs>
        <clipPath id={`played-${id}`}>
          <rect x="0" y="0" width={width * progress} height={height} />
        </clipPath>
        {/* Draw-in: one clip rect sweeps left→right (cheap: one animated node per waveform). */}
        <clipPath id={`reveal-${id}`}>
          <motion.rect
            x="0"
            y="0"
            height={height}
            initial={{ width: reduced ? width : 0 }}
            animate={{ width }}
            transition={{ duration: reduced ? 0 : 0.7, ease: ease.out }}
          />
        </clipPath>
      </defs>
      <motion.g
        clipPath={`url(#reveal-${id})`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: duration.fast }}
      >
        {[false, true].map((played) => (
          <g key={String(played)} clipPath={played ? `url(#played-${id})` : undefined}
            fill={color} opacity={played ? 1 : 0.32}>
            {peaks.map((p, i) => {
              const h = Math.max(2, p * (height - 4));
              return <rect key={i} x={i * (barW + gap)} y={(height - h) / 2} width={barW} height={h} rx={barW / 2} />;
            })}
          </g>
        ))}
      </motion.g>
    </svg>
    </div>
  );
}
