import { AnimatePresence, motion } from "motion/react";
import { Download, Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { formatTime } from "../lib/format";
import { spring } from "../motion/tokens";
import { Waveform } from "./Waveform";

interface Props {
  src: string;
  color?: string;
  downloads?: { label: string; href: string; title?: string }[];
  compact?: boolean;
  autoFocus?: boolean;
  onTime?: (seconds: number) => void;
}

export function AudioPlayer({ src, color, downloads = [], compact = false, autoFocus, onTime }: Props) {
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [length, setLength] = useState(0);

  useEffect(() => {
    setPlaying(false);
    setTime(0);
  }, [src]);

  const toggle = () => {
    const a = audio.current;
    if (!a) return;
    if (a.paused) void a.play();
    else a.pause();
  };

  return (
    <div className={`flex items-center ${compact ? "gap-3" : "gap-4"}`}>
      <motion.button
        type="button"
        onClick={toggle}
        autoFocus={autoFocus}
        aria-label={playing ? "Pause" : "Play"}
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 0.88, transition: spring.snappy }}
        className={`relative flex shrink-0 items-center justify-center rounded-full text-white ${compact ? "size-9" : "size-12"}`}
        style={{ background: color ?? "var(--gradient-primary)", boxShadow: `0 6px 24px -6px ${color ?? "rgb(139 92 246 / .6)"}` }}
      >
        {playing && (
          <motion.span
            aria-hidden
            className="absolute inset-0 rounded-full"
            style={{ border: `2px solid ${color ?? "var(--color-violet-soft)"}` }}
            initial={{ scale: 1, opacity: 0.6 }}
            animate={{ scale: 1.5, opacity: 0 }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
          />
        )}
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={playing ? "pause" : "play"}
            initial={{ scale: 0.4, opacity: 0, rotate: -40 }}
            animate={{ scale: 1, opacity: 1, rotate: 0, transition: spring.snappy }}
            exit={{ scale: 0.4, opacity: 0, rotate: 40 }}
          >
            {playing ? (
              <Pause size={compact ? 15 : 19} fill="currentColor" />
            ) : (
              <Play size={compact ? 15 : 19} fill="currentColor" className="translate-x-[1px]" />
            )}
          </motion.span>
        </AnimatePresence>
      </motion.button>

      <div className="min-w-0 flex-1">
        <Waveform
          source={src}
          height={compact ? 32 : 52}
          color={color}
          progress={length ? time / length : 0}
          onSeek={(f) => {
            if (audio.current && length) audio.current.currentTime = f * length;
          }}
          label="Seek"
        />
        {!compact && (
          <div className="mt-1.5 flex justify-between font-mono text-[11px] text-faint">
            <span>{formatTime(time)}</span>
            <span>{formatTime(length)}</span>
          </div>
        )}
      </div>

      {downloads.length > 0 && (
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          {downloads.map((d) => (
            <a
              key={d.label}
              href={d.href}
              title={d.title ?? `Download ${d.label}`}
              aria-label={d.title ?? `Download ${d.label}`}
              download
              className="inline-flex h-8 items-center gap-1 rounded-full border border-line px-3 text-xs text-muted transition-colors hover:bg-white/[0.06] hover:text-ink"
            >
              <Download size={13} /> {d.label}
            </a>
          ))}
        </div>
      )}

      <audio
        ref={audio}
        src={src}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onLoadedMetadata={(e) => setLength(e.currentTarget.duration)}
        onTimeUpdate={(e) => {
          setTime(e.currentTarget.currentTime);
          onTime?.(e.currentTarget.currentTime);
        }}
      />
    </div>
  );
}
