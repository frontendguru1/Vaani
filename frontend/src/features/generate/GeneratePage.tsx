import * as Slider from "@radix-ui/react-slider";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Plus, Sparkles, WandSparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../../components/AppShell";
import { AudioPlayer } from "../../components/AudioPlayer";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { Orb } from "../../components/Orb";
import { useToast } from "../../components/Toasts";
import { api, ApiError, audioUrl, type GenerationDetail, type JobEvent } from "../../lib/api";
import { formatTime, LANGUAGE_NAMES } from "../../lib/format";
import { useJobEvents } from "../../lib/useJobEvents";
import { voiceColors } from "../../lib/voiceColor";
import { spring, variants } from "../../motion/tokens";
import { ScriptEditor } from "./ScriptEditor";
import { AppliedChips } from "../pronunciation/PronunciationPage";
import { useDebounced } from "../../lib/useDebounced";

const DRAFT_KEY = "vaani.script-draft";
const readDraft = () => {
  try {
    return localStorage.getItem(DRAFT_KEY) ?? "";
  } catch {
    return "";
  }
};

function TranscribeCallout({ voiceId, voiceName, engineLabel }: { voiceId: string; voiceName: string; engineLabel: string }) {
  const [job, setJob] = useState<string | null>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const state = useJobEvents(job, (e) => {
    if (e.status === "succeeded") void qc.invalidateQueries({ queryKey: ["voices"] });
    if (e.status === "failed") toast({ tone: "error", title: "Transcription failed", body: e.error ?? undefined });
  });
  const working = Boolean(job) && !state.done;
  return (
    <div className="rounded-xl border border-okay/30 bg-okay/[0.06] p-3 text-xs">
      <p className="text-muted">
        {engineLabel} needs to know the exact words in one of {voiceName}’s clips. Vaani can transcribe them automatically.
      </p>
      <Button size="sm" className="mt-2" disabled={working}
        onClick={async () => {
          try {
            setJob((await api.transcribe(voiceId)).job_id);
          } catch (e) {
            toast({ tone: "error", title: "Couldn’t start", body: e instanceof ApiError ? e.message : undefined });
          }
        }}>
        <Sparkles size={13} /> {working ? state.latest?.message ?? "Transcribing…" : `Transcribe ${voiceName}’s clips`}
      </Button>
    </div>
  );
}

export function GeneratePage() {
  const [params, setParams] = useSearchParams();
  const voices = useQuery({ queryKey: ["voices"], queryFn: api.voices });
  const engines = useQuery({ queryKey: ["engines"], queryFn: api.engines });
  const ready = useMemo(() => (voices.data ?? []).filter((v) => v.status === "ready"), [voices.data]);

  const [voiceId, setVoiceId] = useState<string | null>(params.get("voice"));
  const voice = ready.find((v) => v.id === voiceId) ?? null;
  const [language, setLanguage] = useState<string>("en");
  const [engine, setEngine] = useState<string | null>(null);
  const [speed, setSpeed] = useState(1);
  const [script, setScript] = useState(readDraft);
  const [job, setJob] = useState<string | null>(null);
  const [gen, setGen] = useState<GenerationDetail | null>(null);
  const [current, setCurrent] = useState<{ index: number; span: [number, number]; total: number } | null>(null);
  const [playSpan, setPlaySpan] = useState<[number, number] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const qc = useQueryClient();

  // Default voice / language / engine once data arrives.
  useEffect(() => {
    if (!voiceId && ready.length) setVoiceId(ready[0].id);
  }, [ready, voiceId]);
  // Depend on the id, not the object: a refetch gives a new object and would reset the
  // language the user picked (review finding).
  const voiceLanguage = voice?.language;
  useEffect(() => {
    if (voiceLanguage) setLanguage(voiceLanguage);
  }, [voice?.id, voiceLanguage]);
  useEffect(() => {
    if (engine || !engines.data) return;
    setEngine(engines.data.find((e) => e.default)?.name ?? engines.data[0]?.name ?? null);
  }, [engines.data, engine]);
  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_KEY, script);
    } catch {
      /* private mode: drafts just aren't remembered */
    }
  }, [script]);

  const onEvent = useCallback(
    (e: JobEvent) => {
      if (e.type === "chunk_started") {
        const d = e.data as { index: number; start: number; end: number; total: number };
        setCurrent({ index: d.index, span: [d.start, d.end], total: d.total });
      }
      if (e.status === "succeeded" && e.generation_id) {
        void api.generation(e.generation_id).then(setGen);
        void qc.invalidateQueries({ queryKey: ["generations"] });
        void qc.invalidateQueries({ queryKey: ["voices"] });
        setCurrent(null);
      }
      if (e.status === "failed") {
        setCurrent(null);
        toast({ tone: "error", title: "Generation failed", body: e.error ?? undefined });
      }
    },
    [qc, toast],
  );
  const state = useJobEvents(job, onEvent);
  const working = Boolean(job) && !state.done;
  const ev = state.latest;

  const debouncedScript = useDebounced(script, 600);
  const pron = useQuery({
    queryKey: ["pron-preview", debouncedScript, language],
    queryFn: () => api.previewPronunciation(debouncedScript, language),
    enabled: debouncedScript.trim().length > 0,
    placeholderData: (prev) => prev,
  });
  const engineInfo = engines.data?.find((e) => e.name === engine);
  // If the chosen engine can't speak the chosen language, switch to one that can.
  useEffect(() => {
    if (!engines.data || !engineInfo || engineInfo.languages.includes(language)) return;
    const fallback = engines.data.find((e) => e.available && e.languages.includes(language));
    if (fallback) setEngine(fallback.name);
  }, [language, engineInfo, engines.data]);
  const colors = voiceColors(voice?.id);
  const chars = script.trim().length;

  const generate = async () => {
    setError(null);
    if (!voice) return setError("Pick a voice first.");
    if (!chars) return setError("Type or paste a script first.");
    setGen(null);
    setPlaySpan(null);
    try {
      const res = await api.generate({
        voice_id: voice.id,
        script,
        language,
        engine: engine ?? undefined,
        settings: speed !== 1 ? { speed } : undefined,
      });
      setJob(res.job_id);
      setCurrent(null);
      if (res.generation.script !== script) setScript(res.generation.script); // server trims
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn’t start generation.");
    }
  };

  if (voices.data && ready.length === 0) {
    return (
      <>
        <PageHeader title="Generate" />
        <div className="glass">
          <EmptyState
            title="Create a voice first"
            body="You need at least one ready voice before you can turn a script into speech."
            action={<Link to="/voices"><Button variant="primary"><Plus size={16} /> Go to Voices</Button></Link>}
          />
        </div>
      </>
    );
  }

  const highlight = working && current ? current.span : playSpan;
  const progress = working ? (ev?.progress ?? 0) : gen ? 1 : null;
  const statusText = working
    ? current
      ? `Speaking sentence ${current.index + 1} of ${current.total}`
      : ev?.message ?? "Starting…"
    : gen
      ? `${formatTime(gen.duration_seconds)} of audio in ${gen.compute_seconds?.toFixed(1)}s`
      : state.failed
        ? "That didn’t work. See the message below."
        : "Ready when you are";

  return (
    <>
      <PageHeader title="Generate" sub="Pick a voice, write what it should say, and listen." />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        {/* Script */}
        <section className="glass p-3 sm:p-4" aria-label="Script editor">
          <ScriptEditor value={script} onChange={setScript} highlight={highlight} readOnly={working} color={colors.solid} />
          <div className="flex flex-wrap items-center justify-between gap-3 px-2 pt-3 text-xs text-faint">
            <span className="font-mono">{chars.toLocaleString()} / 20,000</span>
            <span>Blank lines make longer pauses between paragraphs.</span>
          </div>
          {pron.data && pron.data.applied.length > 0 && script.trim() && (
            <div className="flex flex-wrap items-center gap-2 px-2 pt-3">
              <Link to="/pronunciation" className="text-xs text-faint hover:text-ink">Pronunciation fixes:</Link>
              <AppliedChips applied={pron.data.applied} />
            </div>
          )}
        </section>

        {/* Controls + orb */}
        <section className="flex flex-col gap-5" aria-label="Voice and output">
          <div className="glass space-y-5 p-5">
            <div>
              <h2 className="mb-2 text-sm font-medium">Voice</h2>
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Voice">
                {ready.map((v) => {
                  const c = voiceColors(v.id);
                  const on = v.id === voiceId;
                  return (
                    <motion.button
                      key={v.id}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      disabled={working}
                      onClick={() => { setVoiceId(v.id); setParams({ voice: v.id }, { replace: true }); }}
                      whileTap={{ scale: 0.95 }}
                      className="relative flex items-center gap-2 rounded-full border py-1.5 pr-3.5 pl-1.5 text-sm transition-colors disabled:opacity-60"
                      style={{ borderColor: on ? c.solid : "var(--color-border)", background: on ? c.soft : "transparent" }}
                    >
                      <span className="size-6 rounded-full" style={{ background: c.gradient }} />
                      {v.name}
                    </motion.button>
                  );
                })}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <h2 className="mb-2 text-sm font-medium">Language</h2>
                <div className="flex rounded-xl border border-line p-1" role="radiogroup" aria-label="Language">
                  {(["en", "hi"] as const).map((l) => (
                    <button key={l} type="button" role="radio" aria-checked={language === l} disabled={working}
                      onClick={() => setLanguage(l)}
                      className={`relative flex-1 rounded-lg py-1.5 text-sm ${language === l ? "text-ink" : "text-muted"}`}>
                      {language === l && <motion.span layoutId="gen-lang" className="absolute inset-0 rounded-lg bg-white/[0.09]" transition={spring.gentle} />}
                      <span className="relative" lang={l === "hi" ? "hi" : undefined}>{LANGUAGE_NAMES[l]}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label htmlFor="engine" className="mb-2 block text-sm font-medium">Engine</label>
                <select id="engine" value={engine ?? ""} onChange={(e) => setEngine(e.target.value)} disabled={working}
                  className="field !py-2 text-sm">
                  {engines.data?.map((e) => (
                    <option key={e.name} value={e.name} disabled={!e.available || !e.languages.includes(language)}>
                      {e.label}{!e.available ? " (not set up)" : !e.languages.includes(language) ? ` (no ${LANGUAGE_NAMES[language]})` : ""}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {engineInfo && !engineInfo.available && <p className="text-xs text-okay">{engineInfo.reason}</p>}
            {engineInfo?.needs_transcript && engineInfo.available && voice && (
              voice.has_transcripts ? (
                <p className="text-xs text-muted">
                  {engineInfo.label} copies the voice from a {engineInfo.max_ref_seconds ?? 12}-second transcribed clip. If it sounds off, check the words under Voices → Clips.
                </p>
              ) : (
                <TranscribeCallout voiceId={voice.id} voiceName={voice.name} engineLabel={engineInfo.label} />
              )
            )}

            <div>
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="font-medium" id="speed-label">Speed</span>
                <span className="font-mono text-xs text-muted">{speed.toFixed(2)}×</span>
              </div>
              <Slider.Root value={[speed]} min={0.7} max={1.4} step={0.05} onValueChange={([v]) => setSpeed(v)} disabled={working}
                className="relative flex h-5 touch-none items-center select-none" aria-labelledby="speed-label">
                <Slider.Track className="relative h-1.5 grow rounded-full bg-white/[0.08]">
                  <Slider.Range className="absolute h-full rounded-full" style={{ background: colors.gradient }} />
                </Slider.Track>
                <Slider.Thumb className="block size-4 rounded-full border-2 border-white bg-[var(--color-bg)] shadow" aria-label="Speed" />
              </Slider.Root>
            </div>

            <Button variant="primary" size="lg" className="w-full" onClick={generate} disabled={working || !voice}>
              <WandSparkles size={17} /> {working ? "Generating…" : gen ? "Generate again" : "Generate"}
            </Button>
            <AnimatePresence>
              {error && (
                <motion.p role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1, x: [0, -6, 6, -4, 4, 0] }} exit={{ opacity: 0 }} className="text-sm text-poor">
                  {error}
                </motion.p>
              )}
            </AnimatePresence>
          </div>

          <div className="glass flex flex-col items-center p-6" aria-live="polite">
            <Orb hue={colors.hue} progress={progress} active={working} done={Boolean(gen) && !working} size={190}
              label={working ? `Generating, ${Math.round((ev?.progress ?? 0) * 100)} percent` : "Idle"} />
            <p className="mt-4 text-center text-sm text-muted">{statusText}</p>
            {working && current && (
              <div className="mt-3 flex gap-1" aria-hidden>
                {Array.from({ length: current.total }, (_, i) => (
                  <motion.span key={i} className="h-1 w-5 rounded-full"
                    animate={{ backgroundColor: i < current.index ? colors.solid : i === current.index ? colors.glow : "rgb(255 255 255 / .1)" }} />
                ))}
              </div>
            )}
            {state.failed && ev?.error && <p className="mt-2 text-center text-xs text-poor">{ev.error}</p>}
          </div>
        </section>
      </div>

      {/* Result */}
      <AnimatePresence mode="wait">
        {working && !gen && (
          <motion.div key="skeleton" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="glass mt-6 flex items-center gap-4 p-5" aria-hidden>
            <div className="size-12 animate-pulse rounded-full bg-white/[0.06]" />
            <div className="h-12 flex-1 animate-pulse rounded-lg bg-white/[0.04]" />
          </motion.div>
        )}
        {gen && !working && (
          <motion.section key={gen.id} variants={variants.fadeUp} initial="hidden" animate="show" exit="exit" className="glass mt-6 p-5" aria-label="Result">
            <AudioPlayer
              src={audioUrl.generation(gen.id)}
              color={colors.solid}
              autoFocus
              downloads={[
                { label: "WAV", href: audioUrl.generation(gen.id, "wav", true) },
                { label: "MP3", href: audioUrl.generation(gen.id, "mp3", true) },
              ]}
              onTime={(t) => {
                const c = [...gen.chunks].reverse().find((ch) => (ch.offset_seconds ?? 0) <= t + 0.05);
                setPlaySpan(c && t > 0 ? [c.char_start, c.char_end] : null);
              }}
            />
            <p className="mt-3 text-xs text-faint">
              {gen.chunk_count} sentences, {engines.data?.find((e) => e.name === gen.engine)?.label ?? gen.engine} on{" "}
              {gen.device === "mps" ? "the Apple GPU" : gen.device === "cpu" ? "the CPU" : gen.device}.
            </p>
          </motion.section>
        )}
      </AnimatePresence>
    </>
  );
}
