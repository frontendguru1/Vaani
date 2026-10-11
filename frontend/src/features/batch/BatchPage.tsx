import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { ClipboardPaste, Download, FileUp, Plus, Trash2, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { AudioPlayer } from "../../components/AudioPlayer";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toasts";
import { api, ApiError, audioUrl, type Batch, type BatchItemError, type Generation } from "../../lib/api";
import { hasDevanagari, LANGUAGE_NAMES, relativeDate } from "../../lib/format";
import { findPauses } from "../../lib/pauses";
import { similarityColor } from "../../lib/similarity";
import { voiceColors } from "../../lib/voiceColor";
import { spring, transition, variants } from "../../motion/tokens";
import { newKey, splitBulk, titleFromFile, type DraftItem } from "./split";

const blank = (): DraftItem => ({ key: newKey(), title: "", script: "" });

export function BatchPage() {
  const list = useQuery({
    queryKey: ["batches"],
    queryFn: api.batches,
    refetchInterval: (q) => (q.state.data?.some((b) => !b.finished) ? 1500 : false),
  });
  return (
    <>
      <PageHeader title="Batch" sub="Generate several scripts in one go with the same voice, then download them all as a ZIP." />
      <Composer />
      <section className="mt-12" aria-labelledby="batches-title">
        <h2 id="batches-title" className="mb-4 text-lg font-semibold">Your batches</h2>
        {list.data && list.data.length === 0 && (
          <div className="glass"><EmptyState title="No batches yet" body="Add a few scripts above and press Generate. They’ll run one after another." /></div>
        )}
        <motion.div layout className="space-y-4">
          <AnimatePresence initial={false}>
            {list.data?.map((b) => <BatchCard key={b.id} batch={b} />)}
          </AnimatePresence>
        </motion.div>
      </section>
    </>
  );
}

function Composer() {
  const voices = useQuery({ queryKey: ["voices"], queryFn: api.voices });
  const engines = useQuery({ queryKey: ["engines"], queryFn: api.engines });
  const ready = useMemo(() => (voices.data ?? []).filter((v) => v.status === "ready"), [voices.data]);
  const [voiceId, setVoiceId] = useState<string>("");
  const [language, setLanguage] = useState<"en" | "hi">("en");
  const [engine, setEngine] = useState<string>(""); // "" = recommended
  const [title, setTitle] = useState("");
  const [items, setItems] = useState<DraftItem[]>([blank(), blank()]);
  const [pasting, setPasting] = useState(false);
  const [paste, setPaste] = useState("");
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const vid = voiceId || ready[0]?.id || "";
  const rec = useQuery({ queryKey: ["recommend", vid, language], queryFn: () => api.recommend(vid, language), enabled: Boolean(vid) });

  const filled = items.filter((i) => i.script.trim());
  const update = (key: string, patch: Partial<DraftItem>) => setItems((xs) => xs.map((x) => (x.key === key ? { ...x, ...patch } : x)));

  const create = useMutation({
    mutationFn: () =>
      api.createBatch({
        voice_id: vid,
        language,
        title,
        engine: engine || undefined,
        items: filled.map((i) => ({ title: i.title, script: i.script })),
      }),
    onSuccess: (b) => {
      void qc.invalidateQueries({ queryKey: ["batches"] });
      void qc.invalidateQueries({ queryKey: ["generations"] });
      toast({ tone: "success", title: "Batch started", body: `${b.items.length} scripts queued. They run one after another.` });
      setItems([blank(), blank()]);
      setTitle("");
      setErrors({});
      setFormError(null);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.details) {
        // Map server item indexes (of filled items) back to editor positions.
        const map: Record<number, string> = {};
        for (const d of e.details as BatchItemError[]) {
          const key = filled[d.index]?.key;
          const pos = items.findIndex((i) => i.key === key);
          if (pos >= 0) map[pos] = d.detail;
        }
        setErrors(map);
        setFormError(`${Object.keys(map).length === 1 ? "One script needs" : `${Object.keys(map).length} scripts need`} fixing before anything starts.`);
      } else {
        setFormError(e instanceof ApiError ? e.message : "Couldn’t start the batch.");
      }
    },
  });

  const importFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    const added = await Promise.all(Array.from(files).map(async (f) => ({ key: newKey(), title: titleFromFile(f.name), script: (await f.text()).trim() })));
    setItems((xs) => [...xs.filter((x) => x.script.trim() || x.title.trim()), ...added.filter((a) => a.script)]);
  };

  return (
    <section className="glass space-y-6 p-5 sm:p-6" aria-label="New batch">
      <div className="grid gap-4 md:grid-cols-[1.4fr_1fr_auto_1fr]">
        <label className="block">
          <span className="text-sm font-medium">Batch name <span className="font-normal text-faint">(optional)</span></span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className="field mt-1.5" placeholder="e.g. Road safety lessons" />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Voice</span>
          <select value={vid} onChange={(e) => setVoiceId(e.target.value)} className="field mt-1.5 !py-2.5">
            <optgroup label="Your voices">
              {ready.filter((v) => v.source !== "builtin").map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </optgroup>
            <optgroup label="Built-in">
              {ready.filter((v) => v.source === "builtin").map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </optgroup>
          </select>
        </label>
        <fieldset>
          <legend className="text-sm font-medium">Language</legend>
          <div className="mt-1.5 flex h-11 rounded-xl border border-line p-1" role="radiogroup" aria-label="Language">
            {(["en", "hi"] as const).map((l) => (
              <button key={l} type="button" role="radio" aria-checked={language === l} onClick={() => setLanguage(l)}
                className={`relative rounded-lg px-3 text-sm ${language === l ? "text-ink" : "text-muted"}`}>
                {language === l && <motion.span layoutId="batch-lang" className="absolute inset-0 rounded-lg bg-white/[0.09]" transition={spring.gentle} />}
                <span className="relative" lang={l === "hi" ? "hi" : undefined}>{LANGUAGE_NAMES[l]}</span>
              </button>
            ))}
          </div>
        </fieldset>
        <label className="block">
          <span className="text-sm font-medium">Engine</span>
          <select value={engine} onChange={(e) => setEngine(e.target.value)} className="field mt-1.5 !py-2.5">
            <option value="">Recommended{rec.data ? ` (${engines.data?.find((x) => x.name === rec.data.engine)?.label ?? rec.data.engine})` : ""}</option>
            {engines.data?.filter((x) => x.available && x.languages.includes(language)).map((x) => <option key={x.name} value={x.name}>{x.label}</option>)}
          </select>
        </label>
      </div>

      <div>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h3 className="mr-auto text-sm font-medium">Scripts <span className="font-mono text-faint">{filled.length}</span></h3>
          <Button size="sm" variant="ghost" onClick={() => setPasting((p) => !p)} aria-expanded={pasting}><ClipboardPaste size={14} /> Paste many</Button>
          <Button size="sm" variant="ghost" onClick={() => fileInput.current?.click()}><FileUp size={14} /> Import .txt files</Button>
          <input ref={fileInput} type="file" accept=".txt,text/plain" multiple hidden onChange={(e) => { void importFiles(e.target.files); e.target.value = ""; }} />
        </div>

        <AnimatePresence initial={false}>
          {pasting && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mb-4 overflow-hidden">
              <textarea value={paste} onChange={(e) => setPaste(e.target.value)} rows={6} className="field text-sm" aria-label="Paste many scripts"
                placeholder={"# Lesson 1\nFirst script…\n---\n# Lesson 2\nSecond script…"} />
              <div className="mt-2 flex items-center gap-3">
                <span className="mr-auto text-xs text-faint">Separate scripts with a line of <code className="font-mono">---</code>. A first line starting with <code className="font-mono">#</code> becomes the title.</span>
                <Button size="sm" variant="primary" disabled={!paste.trim()}
                  onClick={() => {
                    const parts = splitBulk(paste);
                    setItems((xs) => [...xs.filter((x) => x.script.trim() || x.title.trim()), ...parts]);
                    setPaste(""); setPasting(false);
                    toast({ tone: "info", title: `Added ${parts.length} scripts` });
                  }}>
                  Split into scripts
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.ol layout className="space-y-3">
          <AnimatePresence initial={false}>
            {items.map((it, i) => {
              const err = errors[i];
              const bad = findPauses(it.script).filter((p) => p.ms == null);
              return (
                <motion.li key={it.key} layout variants={variants.fadeUp} initial="hidden" animate="show" exit={{ opacity: 0, x: -20, transition: transition.exit }}
                  className={`rounded-2xl border p-4 ${err ? "border-poor/60 bg-poor/[0.05]" : "border-line bg-surface-2/50"}`}>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
                    <input value={it.title} onChange={(e) => update(it.key, { title: e.target.value })} maxLength={200}
                      className="field !py-1.5 text-sm" placeholder={`Title (optional), e.g. Part ${i + 1}`} aria-label={`Title of script ${i + 1}`} />
                    <button type="button" onClick={() => setItems((xs) => (xs.length > 1 ? xs.filter((x) => x.key !== it.key) : [blank()]))}
                      aria-label={`Remove script ${i + 1}`} className="rounded-full p-1.5 text-faint hover:bg-white/[0.06] hover:text-ink">
                      <X size={15} />
                    </button>
                  </div>
                  <textarea value={it.script} onChange={(e) => { update(it.key, { script: e.target.value }); if (err) setErrors(({ [i]: _drop, ...rest }) => rest); }}
                    rows={3} className="field mt-2 text-[15px]" aria-label={`Script ${i + 1}`} lang={hasDevanagari(it.script) ? "hi" : undefined}
                    placeholder="What this clip should say. [pause 1s] markers and [Name]: dialogue lines work here too." />
                  {(err || bad.length > 0) && (
                    <motion.p role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1, x: [0, -5, 5, -3, 3, 0] }} className="mt-2 text-xs text-poor">
                      {err ?? `Can’t read ${bad.map((b) => b.raw).join(", ")}. Write it like [pause 1s].`}
                    </motion.p>
                  )}
                </motion.li>
              );
            })}
          </AnimatePresence>
        </motion.ol>
        <Button size="sm" variant="quiet" className="mt-3" onClick={() => setItems((xs) => [...xs, blank()])}><Plus size={14} /> Add a script</Button>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-3 border-t border-line pt-5">
        <AnimatePresence>{formError && <motion.p role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mr-auto text-sm text-poor">{formError}</motion.p>}</AnimatePresence>
        <Button variant="primary" size="lg" disabled={!vid || filled.length === 0 || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? "Starting…" : `Generate ${filled.length || ""} ${filled.length === 1 ? "script" : "scripts"}`}
        </Button>
      </div>
    </section>
  );
}

function statusOf(g: Generation, doneChunks: number) {
  if (g.status === "done") return { label: "Done", color: "var(--color-good)" };
  if (g.status === "failed") return { label: g.error === "Cancelled" ? "Cancelled" : "Failed", color: "var(--color-poor)" };
  if (g.status === "running") return { label: `Generating ${doneChunks}/${g.chunk_count}`, color: "var(--color-cyan)" };
  return { label: "Waiting", color: "var(--color-text-faint)" };
}

function BatchCard({ batch }: { batch: Batch }) {
  const [open, setOpen] = useState(!batch.finished);
  const [format, setFormat] = useState<"wav" | "mp3">("wav");
  const [subs, setSubs] = useState<"srt" | "vtt" | "none">("srt");
  const [confirming, setConfirming] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const colors = voiceColors(batch.voice_id);
  const done = batch.counts.done ?? 0;
  const refresh = () => qc.invalidateQueries({ queryKey: ["batches"] });
  const cancel = useMutation({ mutationFn: () => api.cancelBatch(batch.id), onSuccess: (r) => { void refresh(); toast({ tone: "info", title: `Cancelled ${r.cancelled} waiting scripts` }); } });
  const remove = useMutation({
    mutationFn: () => api.deleteBatch(batch.id),
    onSuccess: () => { void refresh(); void qc.invalidateQueries({ queryKey: ["generations"] }); toast({ tone: "success", title: "Batch deleted" }); },
    onError: (e) => toast({ tone: "error", title: "Couldn’t delete", body: e instanceof ApiError ? e.message : undefined }),
  });

  return (
    <motion.article layout variants={variants.fadeUp} initial="hidden" animate="show" exit={{ opacity: 0, x: -30, transition: transition.exit }} className="glass relative overflow-hidden p-5">
      <span aria-hidden className="absolute inset-y-0 left-0 w-1" style={{ background: colors.gradient }} />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="mr-auto text-left">
          <h3 className="text-base font-semibold">{batch.title}</h3>
          <p className="text-xs text-muted">
            {batch.voice_name ?? "Deleted voice"}, {LANGUAGE_NAMES[batch.language]}, {batch.items.length} scripts, {relativeDate(batch.created_at)}
          </p>
        </button>
        <span className="font-mono text-xs text-muted">{done}/{batch.items.length} done</span>
        {!batch.finished && <Button size="sm" variant="ghost" onClick={() => cancel.mutate()} disabled={cancel.isPending}>Cancel the rest</Button>}
        {done > 0 && (
          <div className="flex items-center gap-1">
            <select value={format} onChange={(e) => setFormat(e.target.value as "wav" | "mp3")} aria-label="Audio format" className="field !w-auto !py-1 text-xs">
              <option value="wav">WAV</option><option value="mp3">MP3</option>
            </select>
            <select value={subs} onChange={(e) => setSubs(e.target.value as "srt" | "vtt" | "none")} aria-label="Subtitles" className="field !w-auto !py-1 text-xs">
              <option value="srt">+ SRT</option><option value="vtt">+ VTT</option><option value="none">No subtitles</option>
            </select>
            <a href={audioUrl.batchZip(batch.id, format, subs)} download
              className="inline-flex h-8 items-center gap-1 rounded-full border border-line px-3 text-xs text-ink transition-colors hover:bg-white/[0.06]">
              <Download size={13} /> Download {batch.finished ? "all" : "finished"} (ZIP)
            </a>
          </div>
        )}
        {confirming ? (
          <span className="flex items-center gap-1">
            <Button size="sm" variant="quiet" onClick={() => setConfirming(false)}>Keep</Button>
            <Button size="sm" variant="danger" onClick={() => remove.mutate()} autoFocus>Delete batch</Button>
          </span>
        ) : (
          <Button size="sm" variant="quiet" aria-label={`Delete ${batch.title}`} onClick={() => setConfirming(true)}><Trash2 size={14} /></Button>
        )}
      </div>

      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/[0.06]" role="progressbar" aria-valuenow={Math.round(batch.progress * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Batch progress">
        <motion.div className="h-full rounded-full" style={{ background: colors.solid, originX: 0 }} animate={{ scaleX: batch.progress }} transition={spring.gentle} />
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.ol initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mt-4 space-y-2 overflow-hidden">
            {batch.items.map((g) => {
              const st = statusOf(g, batch.done_chunks[g.id] ?? 0);
              return (
                <li key={g.id} className="rounded-xl border border-line bg-surface-2/50 p-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-xs text-faint">{String((g.batch_index ?? 0) + 1).padStart(2, "0")}</span>
                    <span className="mr-auto text-sm font-medium">{g.title}</span>
                    {g.similarity != null && (
                      <span className="inline-flex items-center gap-1 text-xs text-muted">
                        <span className="size-1.5 rounded-full" style={{ background: similarityColor(g.similarity) }} />
                        <span className="font-mono">{Math.round(Math.max(0, g.similarity) * 100)}%</span>
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1.5 text-xs" style={{ color: st.color }}>
                      {g.status === "running" && <motion.span className="size-1.5 rounded-full" style={{ background: st.color }} animate={{ scale: [1, 1.7, 1] }} transition={{ duration: 1, repeat: Infinity }} />}
                      {st.label}
                    </span>
                  </div>
                  {g.status === "done" && <div className="mt-2"><AudioPlayer src={audioUrl.generation(g.id)} color={colors.solid} compact /></div>}
                  {g.status === "failed" && g.error !== "Cancelled" && <p className="mt-1 text-xs text-poor">{g.error}</p>}
                </li>
              );
            })}
          </motion.ol>
        )}
      </AnimatePresence>
    </motion.article>
  );
}
