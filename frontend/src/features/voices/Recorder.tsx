import { motion, useReducedMotion } from "motion/react";
import { Mic, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "../../components/Button";
import { formatTime } from "../../lib/format";
import { spring } from "../../motion/tokens";

const TARGET_MIN = 15;
const TARGET_MAX = 60;

function pickMime(): string {
  const options = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return options.find((m) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(m)) ?? "";
}

export function extensionFor(mime: string): string {
  if (mime.includes("mp4")) return "m4a";
  if (mime.includes("ogg")) return "ogg";
  return "webm";
}

/** Mic recording with a live waveform from the Web Audio analyser. */
export function Recorder({ onDone, onCancel }: { onDone: (blob: Blob, seconds: number) => void; onCancel: () => void }) {
  const [state, setState] = useState<"idle" | "recording" | "denied">("idle");
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);
  const cleanup = useRef<() => void>(() => {});
  const reduced = useReducedMotion();

  useEffect(() => () => cleanup.current(), []);

  const start = async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
    } catch {
      setState("denied");
      return;
    }
    const mime = pickMime();
    const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);

    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const history: number[] = [];
    const t0 = performance.now();
    let raf = 0;

    const draw = () => {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += v * v;
      const rms = Math.sqrt(sum / buf.length);
      const lvl = Math.min(1, rms * 6);
      setLevel(lvl);
      setElapsed((performance.now() - t0) / 1000);
      history.push(lvl);
      const c = canvas.current;
      if (c) {
        const g = c.getContext("2d")!;
        const dpr = window.devicePixelRatio || 1;
        const w = c.clientWidth * dpr;
        const h = c.clientHeight * dpr;
        if (c.width !== w) c.width = w;
        if (c.height !== h) c.height = h;
        g.clearRect(0, 0, w, h);
        const barW = 4 * dpr;
        const gap = 2 * dpr;
        const n = Math.floor(w / (barW + gap));
        const recent = history.slice(-n);
        const grad = g.createLinearGradient(0, 0, w, 0);
        grad.addColorStop(0, "#8b5cf6");
        grad.addColorStop(1, "#22d3ee");
        g.fillStyle = grad;
        recent.forEach((v, i) => {
          const bh = Math.max(2 * dpr, v * h * 0.9);
          const x = w - (recent.length - i) * (barW + gap);
          g.beginPath();
          g.roundRect(x, (h - bh) / 2, barW, bh, barW / 2);
          g.fill();
        });
      }
      raf = requestAnimationFrame(draw);
    };

    recorder.onstop = () => {
      const seconds = (performance.now() - t0) / 1000;
      onDone(new Blob(chunks, { type: recorder.mimeType || mime || "audio/webm" }), seconds);
    };

    cleanup.current = () => {
      cancelAnimationFrame(raf);
      if (recorder.state !== "inactive") recorder.stop();
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    };
    recorder.start(250);
    setState("recording");
    draw();
  };

  const stop = () => {
    cleanup.current();
    cleanup.current = () => {};
    setState("idle");
  };

  const pct = Math.min(1, elapsed / TARGET_MAX);
  const reachedMin = elapsed >= TARGET_MIN;

  return (
    <div className="rounded-2xl border border-line bg-surface-2/50 p-5">
      {state === "denied" ? (
        <div className="text-sm">
          <p className="text-poor">Microphone access was blocked.</p>
          <p className="mt-1 text-muted">Allow the microphone for this page in your browser’s site settings, then try again.</p>
          <Button className="mt-4" size="sm" onClick={() => setState("idle")}>Try again</Button>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-5">
            <div className="relative">
              {state === "recording" && !reduced && (
                <motion.span
                  aria-hidden
                  className="absolute inset-0 rounded-full bg-poor"
                  animate={{ scale: [1, 1.25 + level * 0.6], opacity: [0.35, 0] }}
                  transition={{ duration: 1.1, repeat: Infinity, ease: "easeOut" }}
                />
              )}
              <motion.button
                type="button"
                onClick={state === "recording" ? stop : start}
                whileTap={{ scale: 0.9, transition: spring.snappy }}
                whileHover={{ scale: 1.05 }}
                aria-label={state === "recording" ? "Stop recording" : "Start recording"}
                className={`relative flex size-14 items-center justify-center rounded-full text-white ${
                  state === "recording" ? "bg-poor" : "btn-primary"
                }`}
              >
                {state === "recording" ? <Square size={18} fill="currentColor" /> : <Mic size={22} />}
              </motion.button>
            </div>
            <div className="min-w-0 flex-1">
              <canvas ref={canvas} className="h-12 w-full" aria-hidden />
            </div>
          </div>

          <div className="mt-4">
            <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
              <motion.div
                className="h-full rounded-full"
                style={{ background: reachedMin ? "var(--color-good)" : "var(--gradient-primary)", originX: 0 }}
                animate={{ scaleX: pct }}
                transition={{ duration: 0.2 }}
              />
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-muted" aria-live="polite">
              <span className="font-mono text-sm text-ink">{formatTime(elapsed)}</span>
              <span>
                {state !== "recording"
                  ? "Read anything aloud in your normal voice, in a quiet room."
                  : reachedMin
                    ? "That’s enough to work with. Keep going up to a minute for better results."
                    : `Aim for at least ${TARGET_MIN} seconds`}
              </span>
            </div>
          </div>
          {state !== "recording" && (
            <div className="mt-4 flex justify-end">
              <Button size="sm" variant="quiet" onClick={onCancel}>Close recorder</Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
