import { AnimatePresence, motion } from "motion/react";
import { FileAudio, Mic, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ProgressRing } from "../../components/ProgressRing";
import { RatingPill, ScoreRing } from "../../components/ScoreRing";
import { Waveform } from "../../components/Waveform";
import { api, ApiError, type QualityReport } from "../../lib/api";
import { formatBytes, formatTime } from "../../lib/format";
import { spring, transition, variants } from "../../motion/tokens";

export interface PendingFile {
  key: string;
  file: Blob;
  name: string;
  kind: "upload" | "recording";
  transcript: string;
  report?: QualityReport;
}

interface Props {
  item: PendingFile;
  onReport: (key: string, report: QualityReport) => void;
  onRemove: (key: string) => void;
  onTranscript: (key: string, text: string) => void;
}

/** One chosen clip: uploads for a quality check (real progress), then shows its waveform and rating. */
export function FileCard({ item, onReport, onRemove, onTranscript }: Props) {
  const [upload, setUpload] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [showTranscript, setShowTranscript] = useState(Boolean(item.transcript));
  const started = useRef(false);

  useEffect(() => {
    if (started.current || item.report) return;
    started.current = true;
    const ctrl = new AbortController();
    api
      .qualityCheck(item.file, item.name, setUpload, ctrl.signal)
      .then((r) => onReport(item.key, r.report))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Couldn’t read this file."));
    // No abort on unmount: StrictMode double-mounts in dev and the check is cheap.
  }, [item, onReport]);

  const r = item.report;
  const checking = !r && !error;

  return (
    <motion.li
      layout
      variants={variants.fadeUp}
      initial="hidden"
      animate="show"
      exit={{ opacity: 0, scale: 0.95, transition: transition.exit }}
      className="rounded-2xl border border-line bg-surface-2/60 p-4"
    >
      <div className="flex items-center gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/[0.05] text-muted">
          {checking ? (
            <ProgressRing value={upload < 1 ? upload * 0.8 : 0.9} />
          ) : item.kind === "recording" ? (
            <Mic size={16} />
          ) : (
            <FileAudio size={16} />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{item.name}</p>
          <p className="text-xs text-faint">
            {formatBytes(item.file.size)}
            {r && <> · {formatTime(r.duration)} long, {Math.round(r.speech_seconds)}s of speech</>}
            {checking && (upload < 1 ? " · uploading" : " · checking quality")}
          </p>
        </div>
        <AnimatePresence>
          {r && (
            <motion.div initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1, transition: spring.bouncy }}>
              <ScoreRing score={r.score} rating={r.rating} size={44} />
            </motion.div>
          )}
        </AnimatePresence>
        <button
          type="button"
          onClick={() => onRemove(item.key)}
          aria-label={`Remove ${item.name}`}
          className="rounded-full p-1.5 text-faint transition-colors hover:bg-white/[0.06] hover:text-ink"
        >
          <X size={16} />
        </button>
      </div>

      {(r || checking) && (
        <div className="mt-3">
          <Waveform source={r ? item.file : null} sourceKey={item.key} height={36} bars={64} />
        </div>
      )}

      {error && (
        <motion.p variants={variants.shake} animate="shake" className="mt-3 flex items-start gap-2 text-xs text-poor" role="alert">
          <TriangleAlert size={14} className="mt-0.5 shrink-0" /> {error}
        </motion.p>
      )}

      <AnimatePresence>
        {r && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto", transition: transition.enter }}
            className="overflow-hidden"
          >
            <div className="mt-3 flex items-center gap-2">
              <RatingPill rating={r.rating} />
              {r.issues.length === 0 && <span className="text-xs text-muted">Clean speech, no problems found.</span>}
            </div>
            {r.issues.length > 0 && (
              <motion.ul variants={variants.list} initial="hidden" animate="show" className="mt-2 space-y-1">
                {r.issues.map((i) => (
                  <motion.li
                    key={i.code}
                    variants={{ hidden: { opacity: 0, x: -10 }, show: { opacity: 1, x: 0, transition: transition.enter } }}
                    className="flex items-start gap-2 text-xs text-muted"
                  >
                    <span
                      className="mt-1.5 size-1.5 shrink-0 rounded-full"
                      style={{ background: i.severity === "poor" ? "var(--color-poor)" : "var(--color-okay)" }}
                    />
                    {i.message}
                  </motion.li>
                ))}
              </motion.ul>
            )}
            {showTranscript ? (
              <label className="mt-3 block">
                <span className="text-xs text-muted">Exact words spoken in this clip</span>
                <textarea
                  value={item.transcript}
                  onChange={(e) => onTranscript(item.key, e.target.value)}
                  rows={2}
                  className="field mt-1 text-sm"
                  placeholder="Exact words, if you’d rather not rely on automatic transcription"
                />
              </label>
            ) : (
              <button
                type="button"
                onClick={() => setShowTranscript(true)}
                className="mt-2 text-xs text-violet-soft hover:underline"
              >
                Type what was said yourself (optional; it’s transcribed automatically)
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.li>
  );
}
