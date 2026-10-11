import * as Slider from "@radix-ui/react-slider";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { MessagesSquare, Plus, Sparkles, Timer, WandSparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { ScriptEditor, type ScriptEditorHandle } from "./ScriptEditor";
import { similarityColor, similarityLabel } from "../../lib/similarity";
import { findPauses, pauseLabel } from "../../lib/pauses";
import { findSpeakerTags } from "../../lib/dialogue";
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
  const [engineTouched, setEngineTouched] = useState(false); // user picked one by hand
  const [showOriginal, setShowOriginal] = useState(false);
  const [showBuiltins, setShowBuiltins] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [script, setScript] = useState(readDraft);
  const [job, setJob] = useState<string | null>(null);
  const [gen, setGen] = useState<GenerationDetail | null>(null);
  const [current, setCurrent] = useState<{ index: number; span: [number, number]; total: number; voiceId?: string } | null>(null);
  const [playVoice, setPlayVoice] = useState<string | null>(null);
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
  // Recommended engine for this voice + language (measured: F5 sounds much closer for
  // English when the voice has a transcribed clip). Follows voice/language changes unless
  // the user chose an engine themselves.
  const rec = useQuery({
    queryKey: ["recommend", voiceId, language],
    queryFn: () => api.recommend(voiceId!, language),
    enabled: Boolean(voiceId),
  });
  useEffect(() => setEngineTouched(false), [voiceId]);
  useEffect(() => {
    if (engineTouched) return;
    if (rec.data) setEngine(rec.data.engine);
    else if (!engine && engines.data) setEngine(engines.data.find((e) => e.default)?.name ?? engines.data[0]?.name ?? null);
  }, [rec.data, engines.data, engineTouched, engine]);
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
        const d = e.data as { index: number; start: number; end: number; total: number; voice_id?: string };
        setCurrent({ index: d.index, span: [d.start, d.end], total: d.total, voiceId: d.voice_id });
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

  const editor = useRef<ScriptEditorHandle>(null);
  const pauses = useMemo(() => findPauses(script), [script]);
  const badPauses = pauses.filter((p) => p.ms == null);
  const pauseTotal = pauses.reduce((t, p) => t + (p.ms ?? 0), 0);
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
  // Dialogue: speaker tags at line starts, matched to voice names (any status, so a
  // not-ready voice is reported rather than "unknown").
  const allVoices = useMemo(() => voices.data ?? [], [voices.data]);
  const readyIds = useMemo(() => new Set(ready.map((v) => v.id)), [ready]);
  const tags = useMemo(() => findSpeakerTags(script, allVoices), [script, allVoices]);
  const unknownTags = tags.filter((t) => !t.voiceId || !readyIds.has(t.voiceId));
  const speakerIds = useMemo(() => {
    const ids: string[] = [];
    if (tags.length && script.slice(0, tags[0].start).trim() && voice) ids.push(voice.id);
    for (const t of tags) if (t.voiceId && !ids.includes(t.voiceId)) ids.push(t.voiceId);
    return ids;
  }, [tags, script, voice]);
  const decorations = tags.map((t) => ({
    start: t.start,
    end: t.end,
    color: t.voiceId && readyIds.has(t.voiceId) ? voiceColors(t.voiceId).solid : null,
  }));
  const ownCount = ready.filter((v) => v.source !== "builtin").length;
  const builtinCount = ready.length - ownCount;
  const builtinsOpen = showBuiltins || ownCount === 0;
  const nameOf = (id: string) => allVoices.find((v) => v.id === id)?.name ?? "?";
  // The orb and highlight take the colour of whoever is speaking right now.
  const speakingId = working ? (current?.voiceId ?? voice?.id) : (playVoice ?? voice?.id);
  const colors = voiceColors(speakingId);
  const chars = script.trim().length;

  const generate = async () => {
    setError(null);
    if (!voice) return setError("Pick a voice first.");
    if (!chars) return setError("Type or paste a script first.");
    if (unknownTags.length) return setError(`No ready voice called ${unknownTags.map((t) => t.name).join(", ")}. Speaker tags must match a voice name.`);
    if (badPauses.length) return setError(`Can’t read ${badPauses[0].raw}. Write it like [pause 1s] or [pause 500ms].`);
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
      ? `Speaking sentence ${current.index + 1} of ${current.total}${speakerIds.length > 1 && current.voiceId ? `, ${nameOf(current.voiceId)}` : ""}`
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
          <ScriptEditor ref={editor} value={script} onChange={setScript} highlight={highlight} readOnly={working} color={colors.solid} decorations={decorations} />
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-2 pt-3 text-xs text-faint">
            <span className="font-mono">{chars.toLocaleString()} / 20,000</span>
            <div className="flex items-center gap-1" role="group" aria-label="Insert a pause">
              <Timer size={13} aria-hidden />
              <span className="mr-1">Insert pause</span>
              {[500, 1000, 2000, 3000].map((ms) => (
                <button key={ms} type="button" disabled={working}
                  onClick={() => editor.current?.insert(`[pause ${pauseLabel(ms)}]`)}
                  className="rounded-full border border-line px-2 py-0.5 font-mono text-[11px] text-muted transition-colors hover:border-[var(--color-cyan)] hover:text-ink disabled:opacity-40">
                  {pauseLabel(ms)}
                </button>
              ))}
            </div>
            <span className="ml-auto" aria-live="polite">
              {badPauses.length > 0 ? (
                <span className="text-poor">Can’t read {badPauses.map((p) => p.raw).join(", ")}. Write it like [pause 1s].</span>
              ) : pauses.length > 0 ? (
                <span><span className="font-mono text-muted">{pauses.length}</span> {pauses.length === 1 ? "pause" : "pauses"}, <span className="font-mono text-muted">{pauseLabel(pauseTotal)}</span> in total</span>
              ) : (
                "Blank lines make longer pauses between paragraphs."
              )}
            </span>
          </div>
          {ready.length > 1 && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-2 pt-3 text-xs text-faint">
              <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Add a line for a speaker">
                <MessagesSquare size={13} aria-hidden />
                <span className="mr-1">Add a line for</span>
                {ready.filter((v) => v.source !== "builtin" || builtinsOpen || speakerIds.includes(v.id) || v.id === voiceId).map((v) => (
                  <button key={v.id} type="button" disabled={working} onClick={() => editor.current?.insertLine(`[${v.name}]: `)}
                    className="flex items-center gap-1.5 rounded-full border border-line py-0.5 pr-2.5 pl-1 text-[11px] text-muted transition-colors hover:text-ink disabled:opacity-40"
                    style={{ borderColor: voiceColors(v.id).soft }}>
                    <span className="size-3 rounded-full" style={{ background: voiceColors(v.id).gradient }} />
                    {v.name}
                  </button>
                ))}
              </div>
              <span className="ml-auto" aria-live="polite">
                {unknownTags.length > 0 ? (
                  <span className="text-poor">No ready voice called {[...new Set(unknownTags.map((t) => t.name))].join(", ")}.</span>
                ) : speakerIds.length > 1 ? (
                  <span className="flex items-center gap-1.5">
                    Dialogue:
                    {speakerIds.map((id) => (
                      <span key={id} className="flex items-center gap-1 text-muted">
                        <span className="size-2 rounded-full" style={{ background: voiceColors(id).solid }} />
                        {nameOf(id)}
                      </span>
                    ))}
                  </span>
                ) : null}
              </span>
            </div>
          )}
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
                {[...ready]
                  .sort((a, b) => Number(a.source === "builtin") - Number(b.source === "builtin"))
                  .filter((v) => v.source !== "builtin" || builtinsOpen || v.id === voiceId)
                  .map((v, i, arr) => {
                  const firstBuiltin = v.source === "builtin" && (i === 0 || arr[i - 1].source !== "builtin");
                  const c = voiceColors(v.id);
                  const on = v.id === voiceId;
                  return (
                    <span key={v.id} className="contents">
                    {firstBuiltin && <span className="mt-1 w-full text-xs text-faint">Built-in</span>}
                    <motion.button
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
                    </span>
                  );
                })}
              </div>
              {ownCount > 0 && builtinCount > 0 && (
                <button type="button" onClick={() => setShowBuiltins((v) => !v)} aria-expanded={builtinsOpen}
                  className="mt-2 text-xs text-violet-soft hover:underline">
                  {builtinsOpen ? "Hide built-in voices" : `Show ${builtinCount} built-in voices`}
                </button>
              )}
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
                <select id="engine" value={engine ?? ""} onChange={(e) => { setEngine(e.target.value); setEngineTouched(true); }} disabled={working}
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
            {rec.data && engine === rec.data.engine && (
              <p className="text-xs text-muted"><span className="text-good">Recommended.</span> {rec.data.reason}</p>
            )}
            {rec.data?.alternatives.filter((a) => a.engine !== engine).map((a) => (
              <button key={a.engine} type="button" disabled={working}
                onClick={() => { setEngine(a.engine); setEngineTouched(true); }}
                className="block text-left text-xs text-violet-soft hover:underline disabled:opacity-50">
                Try {engines.data?.find((e) => e.name === a.engine)?.label ?? a.engine}: {a.note}
              </button>
            ))}
            {engineInfo?.needs_transcript && engineInfo.available && voice && (
              voice.has_transcripts ? (
                <p className="text-xs text-faint">If it sounds off, check the clip’s words under Voices → Clips.</p>
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
                { label: "SRT", href: audioUrl.subtitles(gen.id, "srt"), title: "Subtitles (SRT)" },
                { label: "VTT", href: audioUrl.subtitles(gen.id, "vtt"), title: "Subtitles (WebVTT)" },
              ]}
              onTime={(t) => {
                const c = [...gen.chunks].reverse().find((ch) => (ch.offset_seconds ?? 0) <= t + 0.05);
                setPlaySpan(c && t > 0 ? [c.char_start, c.char_end] : null);
                setPlayVoice(c && t > 0 ? (c.voice_id ?? gen.voice_id) : null);
              }}
            />
            <div className="mt-4 flex flex-wrap items-center gap-3">
              {gen.similarity != null && gen.voice_id && !(gen.speakers.length > 1) && (
                <span className="inline-flex items-center gap-2 rounded-full border border-line px-3 py-1 text-xs" aria-label="How close it sounds">
                  <span className="size-2 rounded-full" style={{ background: similarityColor(gen.similarity) }} />
                  Sounds {similarityLabel(gen.similarity)} to {voice?.name ?? "the voice"}
                  <span className="font-mono text-muted">{Math.round(Math.max(0, gen.similarity) * 100)}%</span>
                </span>
              )}
              {voice?.has_preview && (
                <Button size="sm" variant="quiet" onClick={() => setShowOriginal((v) => !v)} aria-expanded={showOriginal}>
                  {showOriginal ? "Hide the original" : "Compare with the original"}
                </Button>
              )}
            </div>
            <AnimatePresence initial={false}>
              {showOriginal && voice?.has_preview && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
                  <p className="mt-3 mb-2 text-xs text-faint">Original: a clip {voice.name}’s voice was made from</p>
                  <AudioPlayer src={audioUrl.preview(voice.id)} color="var(--color-text-faint)" compact />
                </motion.div>
              )}
            </AnimatePresence>
            <p className="mt-3 text-xs text-faint">
              {gen.chunk_count} sentences, {engines.data?.find((e) => e.name === gen.engine)?.label ?? gen.engine} on{" "}
              {gen.device === "mps" ? "the Apple GPU" : gen.device === "mlx-gpu" ? "the Apple GPU (MLX)" : gen.device === "cpu" ? "the CPU" : gen.device}.
            </p>
          </motion.section>
        )}
      </AnimatePresence>
    </>
  );
}
