import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toasts";
import { api, ApiError, type PronunciationEntry } from "../../lib/api";
import { hasDevanagari, LANGUAGE_NAMES } from "../../lib/format";
import { useDebounced } from "../../lib/useDebounced";
import { spring, transition, variants } from "../../motion/tokens";

type Lang = "" | "en" | "hi";

/** After any dictionary change: refresh the list and every cached "spoken as" preview
 * (the Try-it box and Generate's chips), or they keep showing the old result. */
function useRefreshDictionary() {
  const qc = useQueryClient();
  return () => Promise.all([
    qc.invalidateQueries({ queryKey: ["pronunciations"] }),
    qc.invalidateQueries({ queryKey: ["pron-preview"] }),
  ]);
}
const langLabel = (l: string | null) => (l ? LANGUAGE_NAMES[l] : "All languages");

export function PronunciationPage() {
  const { data, isLoading } = useQuery({ queryKey: ["pronunciations"], queryFn: api.pronunciations });

  return (
    <>
      <PageHeader
        title="Pronunciation"
        sub="Teach Vaani how to say names, acronyms and words it gets wrong. Your scripts stay as you wrote them; the fix is applied just before speaking."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section className="glass p-5 sm:p-6" aria-label="Dictionary">
          <AddEntry />
          {isLoading && <div className="mt-6 space-y-2">{[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-white/[0.04]" />)}</div>}
          {data && data.length === 0 && (
            <EmptyState title="No fixes yet" body="Add a word above, for example “Vaani” said as “Vaa-nee”, or “IIT” as “I I T”." />
          )}
          {data && data.length > 0 && (
            <motion.ul layout variants={variants.list} initial="hidden" animate="show" className="mt-6 divide-y divide-[var(--color-border)]">
              <AnimatePresence initial={false}>
                {data.map((e) => <EntryRow key={e.id} entry={e} />)}
              </AnimatePresence>
            </motion.ul>
          )}
        </section>
        <TryIt />
      </div>
    </>
  );
}

function LangSelect({ value, onChange, id }: { value: Lang; onChange: (l: Lang) => void; id?: string }) {
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value as Lang)} className="field !py-2 text-sm" aria-label="Applies to">
      <option value="">All languages</option>
      <option value="en">English only</option>
      <option value="hi">हिन्दी only</option>
    </select>
  );
}

function AddEntry() {
  const [term, setTerm] = useState("");
  const [replacement, setReplacement] = useState("");
  const [language, setLanguage] = useState<Lang>("");
  const [error, setError] = useState<string | null>(null);
  const refreshDictionary = useRefreshDictionary();
  const toast = useToast();
  const add = useMutation({
    mutationFn: () => api.addPronunciation({ term, replacement, language: language || null, case_sensitive: false }),
    onSuccess: (e) => {
      setTerm("");
      setReplacement("");
      setError(null);
      void refreshDictionary();
      toast({ tone: "success", title: "Added", body: `“${e.term}” will be said as “${e.replacement}”.` });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Couldn’t add that."),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
    >
      <div className="grid items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
        <label className="block">
          <span className="text-sm font-medium">Word or phrase</span>
          <input value={term} onChange={(e) => setTerm(e.target.value)} maxLength={200} className="field mt-1.5"
            placeholder="Vaani" lang={hasDevanagari(term) ? "hi" : undefined} />
        </label>
        <ArrowRight size={18} className="mb-3 hidden text-faint sm:block" aria-hidden />
        <label className="block">
          <span className="text-sm font-medium">Say it as</span>
          <input value={replacement} onChange={(e) => setReplacement(e.target.value)} maxLength={400} className="field mt-1.5"
            placeholder="Vaa-nee" lang={hasDevanagari(replacement) ? "hi" : undefined} />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <div className="w-44"><LangSelect value={language} onChange={setLanguage} /></div>
        <AnimatePresence>
          {error && (
            <motion.p key={error} role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1, x: [0, -6, 6, -4, 4, 0] }} exit={{ opacity: 0 }} className="text-sm text-poor">
              {error}
            </motion.p>
          )}
        </AnimatePresence>
        <Button type="submit" variant="primary" className="ml-auto" disabled={!term.trim() || !replacement.trim() || add.isPending}>
          <Plus size={15} /> Add
        </Button>
      </div>
      <p className="mt-2 text-xs text-faint">Matches whole words, ignoring upper/lower case. Spell the sound the way you’d write it for a friend: hyphens and spaces help.</p>
    </form>
  );
}

function EntryRow({ entry }: { entry: PronunciationEntry }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [term, setTerm] = useState(entry.term);
  const [replacement, setReplacement] = useState(entry.replacement);
  const [language, setLanguage] = useState<Lang>((entry.language ?? "") as Lang);
  const refresh = useRefreshDictionary();
  const toast = useToast();
  const save = useMutation({
    mutationFn: () => api.updatePronunciation(entry.id, { term, replacement, language: language || null }),
    onSuccess: () => { setEditing(false); void refresh(); },
    onError: (e) => toast({ tone: "error", title: "Couldn’t save", body: e instanceof ApiError ? e.message : undefined }),
  });
  const toggleCase = useMutation({
    mutationFn: () => api.updatePronunciation(entry.id, { case_sensitive: !entry.case_sensitive }),
    onSuccess: () => void refresh(),
  });
  const remove = useMutation({
    mutationFn: () => api.deletePronunciation(entry.id),
    onSuccess: () => void refresh(),
    onError: () => toast({ tone: "error", title: "Couldn’t delete" }),
  });

  return (
    <motion.li layout variants={variants.fadeUp} exit={{ opacity: 0, x: -24, transition: transition.exit }} className="py-3">
      {editing ? (
        <form className="grid items-center gap-2 sm:grid-cols-[1fr_1fr_150px_auto]" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <input value={term} onChange={(e) => setTerm(e.target.value)} className="field !py-2 text-sm" aria-label="Word" autoFocus />
          <input value={replacement} onChange={(e) => setReplacement(e.target.value)} className="field !py-2 text-sm" aria-label="Say it as" />
          <LangSelect value={language} onChange={setLanguage} />
          <div className="flex gap-1">
            <Button type="submit" size="sm" variant="primary" aria-label="Save" disabled={save.isPending}><Check size={14} /></Button>
            <Button size="sm" variant="quiet" aria-label="Cancel" onClick={() => setEditing(false)}><X size={14} /></Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="font-medium" lang={hasDevanagari(entry.term) ? "hi" : undefined}>{entry.term}</span>
          <ArrowRight size={14} className="text-faint" aria-label="said as" />
          <span className="text-violet-soft" lang={hasDevanagari(entry.replacement) ? "hi" : undefined}>{entry.replacement}</span>
          <span className="rounded-full border border-line px-2 py-0.5 text-[11px] text-muted">{langLabel(entry.language)}</span>
          <AnimatePresence mode="wait" initial={false}>
            {confirming ? (
              <motion.div key="c" className="ml-auto flex items-center gap-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <span className="text-xs text-muted">Remove?</span>
                <Button size="sm" variant="quiet" onClick={() => setConfirming(false)}>Keep</Button>
                <Button size="sm" variant="danger" autoFocus onClick={() => remove.mutate()}>Remove</Button>
              </motion.div>
            ) : (
              <motion.div key="a" className="ml-auto flex items-center gap-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <motion.button
                  type="button"
                  onClick={() => toggleCase.mutate()}
                  whileTap={{ scale: 0.92, transition: spring.snappy }}
                  aria-pressed={entry.case_sensitive}
                  title={entry.case_sensitive ? "Matches exact upper/lower case" : "Ignores upper/lower case"}
                  className={`rounded-full border px-2.5 py-1 text-[11px] transition-colors ${entry.case_sensitive ? "border-[var(--color-violet-soft)] text-ink" : "border-line text-faint hover:text-muted"}`}
                >
                  {entry.case_sensitive ? "Exact case" : "Any case"}
                </motion.button>
                <Button size="sm" variant="quiet" aria-label={`Edit ${entry.term}`} onClick={() => { setTerm(entry.term); setReplacement(entry.replacement); setLanguage((entry.language ?? "") as Lang); setEditing(true); }}>
                  <Pencil size={14} />
                </Button>
                <Button size="sm" variant="quiet" aria-label={`Remove ${entry.term}`} onClick={() => setConfirming(true)}>
                  <Trash2 size={14} />
                </Button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </motion.li>
  );
}

function TryIt() {
  const [text, setText] = useState("Welcome to Vaani! We met at IIT last year.");
  const [language, setLanguage] = useState<"en" | "hi">("en");
  const debounced = useDebounced(text, 300);
  const { data } = useQuery({
    queryKey: ["pron-preview", debounced, language],
    queryFn: () => api.previewPronunciation(debounced, language),
    enabled: debounced.trim().length > 0,
    placeholderData: (prev) => prev,
  });

  return (
    <section className="glass h-fit p-5 sm:p-6" aria-label="Try it">
      <h2 className="text-base font-semibold">Try it</h2>
      <p className="mt-1 text-sm text-muted">Type a sentence to see what the voice will actually be given.</p>
      <div className="mt-4 flex rounded-xl border border-line p-1" role="radiogroup" aria-label="Language">
        {(["en", "hi"] as const).map((l) => (
          <button key={l} type="button" role="radio" aria-checked={language === l} onClick={() => setLanguage(l)}
            className={`relative flex-1 rounded-lg py-1.5 text-sm ${language === l ? "text-ink" : "text-muted"}`}>
            {language === l && <motion.span layoutId="try-lang" className="absolute inset-0 rounded-lg bg-white/[0.09]" transition={spring.gentle} />}
            <span className="relative" lang={l === "hi" ? "hi" : undefined}>{LANGUAGE_NAMES[l]}</span>
          </button>
        ))}
      </div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} className="field mt-3 text-[15px]"
        aria-label="Sentence to try" lang={hasDevanagari(text) ? "hi" : undefined} />
      <div className="mt-3 rounded-xl border border-line bg-surface-2/60 p-3" aria-live="polite">
        <p className="text-xs text-faint">Spoken as</p>
        <p className="mt-1 text-[15px]" lang={hasDevanagari(data?.text ?? "") ? "hi" : undefined}>{data?.text ?? text}</p>
      </div>
      {data && data.applied.length > 0 && <AppliedChips applied={data.applied} className="mt-3" />}
    </section>
  );
}

export function AppliedChips({ applied, className = "" }: { applied: { term: string; replacement: string; count: number }[]; className?: string }) {
  return (
    <motion.ul layout className={`flex flex-wrap gap-1.5 ${className}`}>
      <AnimatePresence initial={false}>
        {applied.map((a) => (
          <motion.li key={a.term} layout initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1, transition: spring.snappy }}
            exit={{ opacity: 0, scale: 0.85 }} className="rounded-full bg-[var(--color-violet)]/15 px-2.5 py-1 text-xs text-violet-soft">
            <span lang={hasDevanagari(a.term) ? "hi" : undefined}>{a.term}</span> → <span lang={hasDevanagari(a.replacement) ? "hi" : undefined}>{a.replacement}</span>
            {a.count > 1 && <span className="ml-1 font-mono text-faint">×{a.count}</span>}
          </motion.li>
        ))}
      </AnimatePresence>
    </motion.ul>
  );
}
