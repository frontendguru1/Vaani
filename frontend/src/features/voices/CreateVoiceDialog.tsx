import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Check, Mic } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import { RatingPill, ScoreRing } from "../../components/ScoreRing";
import { useToast } from "../../components/Toasts";
import { api, ApiError, type JobEvent, type QualityReport, type VoiceSummaryReport } from "../../lib/api";
import { useJobEvents } from "../../lib/useJobEvents";
import { getHealth } from "../health/api";
import { voiceHue } from "../../lib/voiceColor";
import { spring, transition, variants } from "../../motion/tokens";
import { Dropzone } from "./Dropzone";
import { FileCard, type PendingFile } from "./FileCard";
import { extensionFor, Recorder } from "./Recorder";
import { Flourish, Voiceprint } from "./Voiceprint";

const ALL_STEPS = [
  { key: "cleaning", label: "Cleaning the audio" },
  { key: "quality", label: "Checking quality" },
  { key: "transcribing", label: "Transcribing what was said" },
  { key: "voiceprint", label: "Extracting the voiceprint" },
  { key: "saving", label: "Saving" },
] as const;

function stepIndex(steps: readonly { key: string }[], step: string | null): number {
  const key = step === "loading_model" ? "voiceprint" : step;
  const i = steps.findIndex((s) => s.key === key);
  return i < 0 ? 0 : i;
}

export function CreateVoiceDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [name, setName] = useState("");
  const [language, setLanguage] = useState<"en" | "hi">("en");
  const [description, setDescription] = useState("");
  const [consent, setConsent] = useState("");
  const [denoise, setDenoise] = useState(false);
  const [files, setFiles] = useState<PendingFile[]>([]);
  const [recording, setRecording] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [shakeKey, setShakeKey] = useState(0);
  const [job, setJob] = useState<{ id: string; voiceId: string } | null>(null);
  const [summary, setSummary] = useState<VoiceSummaryReport | null>(null);
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth });
  const t = health.data?.transcription;
  const STEPS = ALL_STEPS.filter((s) => s.key !== "transcribing" || (t?.available && t.on_create));

  const reset = () => {
    setName(""); setDescription(""); setConsent(""); setFiles([]); setDenoise(false);
    setRecording(false); setUploadPct(null); setFormError(null); setJob(null); setSummary(null);
  };

  const onEvent = useCallback(
    (e: JobEvent) => {
      if (e.type === "quality") setSummary(e.data.summary as VoiceSummaryReport);
      if (e.status === "succeeded" || e.status === "failed") void qc.invalidateQueries({ queryKey: ["voices"] });
      if (e.status === "succeeded") toast({ tone: "success", title: "Voice ready", body: `${name} is ready to use.` });
    },
    [qc, toast, name],
  );
  const jobState = useJobEvents(job?.id ?? null, onEvent);
  const ev = jobState.latest;

  const addFiles = (list: File[]) =>
    setFiles((fs) => [
      ...fs,
      ...list.map((f) => ({ key: `${f.name}-${f.size}-${Math.random()}`, file: f, name: f.name, kind: "upload" as const, transcript: "" })),
    ]);
  const onReport = useCallback(
    (key: string, report: QualityReport) => setFiles((fs) => fs.map((f) => (f.key === key ? { ...f, report } : f))),
    [],
  );
  const onRemove = useCallback((key: string) => setFiles((fs) => fs.filter((f) => f.key !== key)), []);
  const onTranscript = useCallback(
    (key: string, transcript: string) => setFiles((fs) => fs.map((f) => (f.key === key ? { ...f, transcript } : f))),
    [],
  );

  const speech = useMemo(() => files.reduce((s, f) => s + (f.report?.speech_seconds ?? 0), 0), [files]);

  const submit = async () => {
    const problems = [
      !name.trim() && "Give the voice a name.",
      consent.trim().length < 10 && "Write a consent note: whose voice is this, and do you have permission?",
      files.length === 0 && "Add at least one audio file or recording.",
    ].filter(Boolean) as string[];
    if (problems.length) {
      setFormError(problems[0]);
      setShakeKey((k) => k + 1);
      return;
    }
    setFormError(null);
    const form = new FormData();
    form.append("name", name);
    form.append("language", language);
    form.append("consent_note", consent);
    form.append("description", description);
    form.append("denoise", String(denoise));
    files.forEach((f) => {
      form.append("files", f.file, f.name);
      form.append("kinds", f.kind);
      form.append("transcripts", f.transcript);
    });
    try {
      setUploadPct(0);
      const res = await api.createVoice(form, setUploadPct);
      setJob({ id: res.job_id, voiceId: res.voice.id });
      void qc.invalidateQueries({ queryKey: ["voices"] });
    } catch (e) {
      setUploadPct(null);
      setFormError(e instanceof ApiError ? e.message : "Upload failed.");
      setShakeKey((k) => k + 1);
    }
  };

  const hue = job ? voiceHue(job.voiceId) : 262;
  const processing = Boolean(job) && !jobState.done;
  const ready = jobState.done && !jobState.failed;
  const current = stepIndex(STEPS, ev?.step ?? null);
  const progressInStep = ev ? ev.progress : 0;

  return (
    <Modal
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o && !processing) setTimeout(reset, 300);
      }}
      title={job ? (ready ? `${name} is ready` : jobState.failed ? "Something went wrong" : `Creating ${name}`) : "New voice"}
      description={job ? undefined : "Add a few clips of one person speaking. Everything stays on this Mac."}
      wide
      locked={processing}
    >
      <AnimatePresence mode="wait">
        {!job ? (
          <motion.div key="form" exit={{ opacity: 0, transition: transition.exit }} className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
              <label className="block">
                <span className="text-sm font-medium">Name</span>
                <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className="field mt-1.5" placeholder="e.g. Papa, Meera, Me" />
              </label>
              <fieldset>
                <legend className="text-sm font-medium">Language</legend>
                <div className="mt-1.5 flex h-11 rounded-xl border border-line bg-surface-2/60 p-1" role="radiogroup">
                  {(["en", "hi"] as const).map((l) => (
                    <button
                      key={l}
                      type="button"
                      role="radio"
                      aria-checked={language === l}
                      onClick={() => setLanguage(l)}
                      className={`relative rounded-lg px-4 text-sm ${language === l ? "text-ink" : "text-muted"}`}
                    >
                      {language === l && <motion.span layoutId="lang-pill" className="absolute inset-0 rounded-lg bg-white/[0.09]" transition={spring.gentle} />}
                      <span className="relative" lang={l === "hi" ? "hi" : undefined}>{l === "en" ? "English" : "हिन्दी"}</span>
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>

            <label className="block">
              <span className="text-sm font-medium">Whose voice is this, and do you have their permission?</span>
              <textarea
                value={consent}
                onChange={(e) => setConsent(e.target.value)}
                rows={2}
                className="field mt-1.5"
                placeholder="e.g. My own voice. / My daughter Meera, recorded with her and her mother’s permission."
              />
              <span className="mt-1 block text-xs text-faint">Required. It’s saved with the voice, and the voice can’t be used without it.</span>
            </label>

            <label className="block">
              <span className="text-sm font-medium">Description <span className="font-normal text-faint">(optional)</span></span>
              <input value={description} onChange={(e) => setDescription(e.target.value)} className="field mt-1.5" placeholder="Bedtime-story voice, recorded in the study" />
            </label>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium">Audio</span>
                {!recording && (
                  <Button size="sm" variant="ghost" onClick={() => setRecording(true)}>
                    <Mic size={14} /> Record with the microphone
                  </Button>
                )}
              </div>
              <AnimatePresence initial={false}>
                {recording && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mb-3 overflow-hidden">
                    <Recorder
                      onCancel={() => setRecording(false)}
                      onDone={(blob) => {
                        const n = files.filter((f) => f.kind === "recording").length + 1;
                        setFiles((fs) => [...fs, { key: `rec-${Date.now()}`, file: blob, name: `Recording ${n}.${extensionFor(blob.type)}`, kind: "recording", transcript: "" }]);
                      }}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
              <Dropzone onFiles={addFiles} />
              <motion.ul layout className="mt-3 space-y-2">
                <AnimatePresence initial={false}>
                  {files.map((f) => (
                    <FileCard key={f.key} item={f} onReport={onReport} onRemove={onRemove} onTranscript={onTranscript} />
                  ))}
                </AnimatePresence>
              </motion.ul>
              {files.length > 0 && <SpeechMeter seconds={speech} />}
            </div>

            <label className="flex cursor-pointer items-center gap-3 text-sm">
              <input type="checkbox" checked={denoise} onChange={(e) => setDenoise(e.target.checked)} className="size-4 accent-[var(--color-violet)]" />
              <span>
                Reduce background noise
                <span className="block text-xs text-faint">Helps with hum or hiss. Leave it off for clean recordings, since it can dull the voice slightly.</span>
              </span>
            </label>

            <div className="flex flex-wrap items-center justify-end gap-3 border-t border-line pt-5">
              <AnimatePresence>
                {formError && (
                  <motion.p key={shakeKey} role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1, x: [0, -6, 6, -4, 4, 0] }} exit={{ opacity: 0 }} className="mr-auto text-sm text-poor">
                    {formError}
                  </motion.p>
                )}
              </AnimatePresence>
              <Button variant="primary" size="lg" onClick={submit} disabled={uploadPct !== null}>
                {uploadPct !== null ? `Uploading ${Math.round(uploadPct * 100)}%` : "Create voice"}
              </Button>
            </div>
          </motion.div>
        ) : (
          <motion.div key="progress" initial={{ opacity: 0 }} animate={{ opacity: 1, transition: transition.enter }} className="grid items-center gap-8 sm:grid-cols-[auto_1fr]">
            <div className="relative">
              <Voiceprint hue={hue} progress={ready ? 1 : progressInStep} ready={ready} seed={job.voiceId} />
              {ready && <Flourish hue={hue} />}
            </div>
            <div aria-live="polite">
              <ol className="space-y-3">
                {STEPS.map((s, i) => {
                  const state = ready || i < current ? "done" : i === current && !jobState.failed ? "active" : jobState.failed && i === current ? "failed" : "todo";
                  return (
                    <li key={s.key} className="flex items-center gap-3">
                      <motion.span
                        className="flex size-7 shrink-0 items-center justify-center rounded-full border text-xs"
                        animate={{
                          borderColor: state === "done" ? "var(--color-good)" : state === "active" ? `oklch(0.72 0.17 ${hue})` : state === "failed" ? "var(--color-poor)" : "var(--color-border)",
                          backgroundColor: state === "done" ? "rgb(52 211 153 / .15)" : "rgb(0 0 0 / 0)",
                        }}
                      >
                        {state === "done" ? (
                          <motion.span initial={{ scale: 0 }} animate={{ scale: 1, transition: spring.bouncy }}>
                            <Check size={14} className="text-good" />
                          </motion.span>
                        ) : state === "active" ? (
                          <motion.span className="size-2 rounded-full" style={{ background: `oklch(0.72 0.17 ${hue})` }} animate={{ scale: [1, 1.6, 1] }} transition={{ duration: 1, repeat: Infinity }} />
                        ) : (
                          <span className="text-faint">{i + 1}</span>
                        )}
                      </motion.span>
                      <span className={state === "todo" ? "text-faint" : state === "failed" ? "text-poor" : "text-ink"}>{s.label}</span>
                    </li>
                  );
                })}
              </ol>
              <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                <motion.div className="h-full rounded-full" style={{ background: `oklch(0.72 0.17 ${hue})`, originX: 0 }} animate={{ scaleX: ready ? 1 : progressInStep }} transition={spring.gentle} />
              </div>
              <p className="mt-2 text-sm text-muted">{jobState.failed ? ev?.error : ev?.message ?? "Starting…"}</p>

              <AnimatePresence>
                {summary && (
                  <motion.div variants={variants.fadeUp} initial="hidden" animate="show" className="mt-5 flex items-start gap-4 rounded-2xl border border-line bg-surface-2/60 p-4">
                    <ScoreRing score={summary.score} rating={summary.rating} size={56} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <RatingPill rating={summary.rating} />
                        <span className="text-xs text-muted">{Math.round(summary.speech_seconds)}s of speech in total</span>
                      </div>
                      {summary.issues.map((i) => (
                        <motion.p key={i.code} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className="mt-1.5 text-xs text-muted">{i.message}</motion.p>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {jobState.done && (
                <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-6 flex flex-wrap gap-3">
                  {ready ? (
                    <>
                      <Button variant="primary" onClick={() => { onOpenChange(false); setTimeout(reset, 300); navigate(`/generate?voice=${job.voiceId}`); }}>
                        Generate with this voice
                      </Button>
                      <Button onClick={() => { onOpenChange(false); setTimeout(reset, 300); }}>Done</Button>
                    </>
                  ) : (
                    <Button onClick={() => { setJob(null); setSummary(null); setUploadPct(null); }}>Back to the form</Button>
                  )}
                </motion.div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </Modal>
  );
}

function SpeechMeter({ seconds }: { seconds: number }) {
  const pct = Math.min(1, seconds / 60);
  const color = seconds >= 15 ? "var(--color-good)" : seconds >= 6 ? "var(--color-okay)" : "var(--color-poor)";
  return (
    <div className="mt-4">
      <div className="relative h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div className="h-full rounded-full" style={{ background: color, originX: 0 }} animate={{ scaleX: pct }} transition={spring.gentle} />
        <span className="absolute top-0 h-full w-px bg-white/30" style={{ left: "25%" }} aria-hidden />
      </div>
      <p className="mt-1.5 text-xs text-muted">
        <span className="font-mono text-ink">{Math.round(seconds)}s</span> of speech so far.{" "}
        {seconds < 15 ? "15 seconds is the minimum we recommend; up to 60 is better." : seconds <= 60 ? "Good amount." : "More than enough. The cleanest minute is used."}
      </p>
    </div>
  );
}
