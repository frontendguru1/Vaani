import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Check, Pencil, Sparkles } from "lucide-react";
import { useCallback, useState } from "react";
import { AudioPlayer } from "../../components/AudioPlayer";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { RatingPill } from "../../components/ScoreRing";
import { useToast } from "../../components/Toasts";
import { api, ApiError, audioUrl, type JobEvent, type Sample, type Voice } from "../../lib/api";
import { formatTime, hasDevanagari } from "../../lib/format";
import { useJobEvents } from "../../lib/useJobEvents";
import { voiceColors } from "../../lib/voiceColor";
import { spring, transition, variants } from "../../motion/tokens";

/** Every clip of a voice: play it, read what Whisper heard, correct it phrase by phrase. */
export function ClipsDialog({ voice, open, onOpenChange }: { voice: Voice; open: boolean; onOpenChange: (o: boolean) => void }) {
  const colors = voiceColors(voice.id);
  const qc = useQueryClient();
  const toast = useToast();
  const detail = useQuery({ queryKey: ["voice", voice.id], queryFn: () => api.voice(voice.id), enabled: open });
  const [job, setJob] = useState<string | null>(null);

  const onEvent = useCallback(
    (e: JobEvent) => {
      if (e.status === "succeeded") {
        void qc.invalidateQueries({ queryKey: ["voice", voice.id] });
        void qc.invalidateQueries({ queryKey: ["voices"] });
        toast({ tone: "success", title: "Transcribed", body: `${voice.name}’s clips now have transcripts.` });
        setJob(null);
      }
      if (e.status === "failed") {
        toast({ tone: "error", title: "Transcription failed", body: e.error ?? undefined });
        setJob(null);
      }
    },
    [qc, toast, voice.id, voice.name],
  );
  const state = useJobEvents(job, onEvent);

  const start = async (force = false) => {
    try {
      setJob((await api.transcribe(voice.id, force)).job_id);
    } catch (e) {
      toast({ tone: "error", title: "Couldn’t start transcription", body: e instanceof ApiError ? e.message : undefined });
    }
  };

  const samples = detail.data?.samples ?? [];
  const anyTranscribed = samples.some((s) => s.transcript_segments?.length);
  const working = Boolean(job) && !state.done;

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={`${voice.name}’s clips`} wide
      description="What Vaani heard in each clip. Fix any mistakes: F5 and IndicF5 need the words to be exact.">
      {voice.source === "builtin" ? (
        <p className="mb-5 text-sm text-muted">
          This built-in voice comes ready-made with the XTTS-v2 model. Its sample clip below was spoken from a known script, so its transcript is exact.
        </p>
      ) : (
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Button variant={anyTranscribed ? "ghost" : "primary"} onClick={() => start(anyTranscribed)} disabled={working}>
          <Sparkles size={15} /> {working ? "Transcribing…" : anyTranscribed ? "Transcribe again" : "Transcribe clips"}
        </Button>
        <AnimatePresence>
          {working && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex min-w-48 flex-1 items-center gap-3" aria-live="polite">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                <motion.div className="h-full rounded-full" style={{ background: colors.solid, originX: 0 }}
                  animate={{ scaleX: state.latest?.progress ?? 0.02 }} transition={spring.gentle} />
              </div>
              <span className="text-xs text-muted">{state.latest?.message ?? "Starting…"}</span>
            </motion.div>
          )}
        </AnimatePresence>
        {anyTranscribed && !working && <span className="text-xs text-faint">Transcribing again keeps the clips whose words you’ve corrected.</span>}
      </div>
      )}

      {detail.isLoading && <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="h-28 animate-pulse rounded-2xl bg-white/[0.04]" />)}</div>}
      <motion.ul variants={variants.list} initial="hidden" animate="show" className="space-y-3">
        {samples.map((s) => <ClipRow key={s.id} voice={voice} sample={s} color={colors.solid} />)}
      </motion.ul>
    </Modal>
  );
}

function ClipRow({ voice, sample, color }: { voice: Voice; sample: Sample; color: string }) {
  const [editing, setEditing] = useState(false);
  const segs = sample.transcript_segments ?? [];
  const [drafts, setDrafts] = useState<string[]>(segs.map((s) => s.text));
  const [saving, setSaving] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();

  const save = async () => {
    setSaving(true);
    try {
      await api.correctTranscript(voice.id, sample.id, drafts);
      await qc.invalidateQueries({ queryKey: ["voice", voice.id] });
      setEditing(false);
      toast({ tone: "success", title: "Transcript saved" });
    } catch (e) {
      toast({ tone: "error", title: "Couldn’t save", body: e instanceof ApiError ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.li variants={variants.fadeUp} className="rounded-2xl border border-line bg-surface-2/60 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="truncate text-sm font-medium">{sample.original_filename}</span>
        <span className="font-mono text-xs text-faint">{formatTime(sample.duration_seconds)}</span>
        {sample.quality && <RatingPill rating={sample.quality.rating} />}
        {sample.transcript_source && (
          <span className="text-xs text-faint">
            {sample.transcript_source === "user" ? "Checked by you" : sample.transcript_source === "builtin" ? "Exact script" : "Transcribed automatically"}
          </span>
        )}
        {segs.length > 0 && !editing && sample.transcript_source !== "builtin" && (
          <Button size="sm" variant="quiet" className="ml-auto" onClick={() => { setDrafts(segs.map((x) => x.text)); setEditing(true); }}>
            <Pencil size={13} /> Correct
          </Button>
        )}
      </div>
      {sample.has_audio && <AudioPlayer src={audioUrl.sample(voice.id, sample.id)} color={color} compact />}

      <div className="mt-3">
        {segs.length === 0 ? (
          <p className="text-sm text-faint">{sample.transcript ?? "Not transcribed yet."}</p>
        ) : (
          <ol className="space-y-1.5">
            {segs.map((seg, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span className="w-12 shrink-0 pt-0.5 font-mono text-[11px] text-faint">{formatTime(seg.start)}</span>
                {editing ? (
                  <input value={drafts[i] ?? ""} onChange={(e) => setDrafts((d) => d.map((x, j) => (j === i ? e.target.value : x)))}
                    lang={hasDevanagari(drafts[i] ?? "") ? "hi" : undefined} className="field !py-1.5 text-sm" aria-label={`Phrase at ${formatTime(seg.start)}`} />
                ) : (
                  <span lang={hasDevanagari(seg.text) ? "hi" : undefined} className="text-ink/90">{seg.text}</span>
                )}
              </li>
            ))}
          </ol>
        )}
        <AnimatePresence>
          {editing && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0, transition: transition.enter }} exit={{ opacity: 0 }} className="mt-3 flex justify-end gap-2">
              <Button size="sm" variant="quiet" onClick={() => setEditing(false)}>Cancel</Button>
              <Button size="sm" variant="primary" onClick={save} disabled={saving}>
                <Check size={13} /> {saving ? "Saving…" : "Save transcript"}
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.li>
  );
}
