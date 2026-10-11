import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Plus, RotateCcw } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toasts";
import { api, ApiError, type Voice } from "../../lib/api";
import { spring, variants } from "../../motion/tokens";
import { CreateVoiceDialog } from "./CreateVoiceDialog";
import { VoiceCard } from "./VoiceCard";

type Filter = "all" | "female" | "male";
const GRID = "grid grid-cols-[repeat(auto-fill,minmax(290px,1fr))] gap-5";

export function VoicesPage() {
  const [creating, setCreating] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const qc = useQueryClient();
  const toast = useToast();
  const { data: voices, isLoading, isError, refetch } = useQuery({
    queryKey: ["voices"],
    queryFn: api.voices,
    // Keep polling while something is still processing in the background.
    refetchInterval: (q) => (q.state.data?.some((v) => v.status === "processing") ? 2000 : false),
  });
  const missing = useQuery({ queryKey: ["builtin-missing"], queryFn: api.builtinMissing });

  const mine = (voices ?? []).filter((v) => v.source !== "builtin");
  const builtins = (voices ?? []).filter((v) => v.source === "builtin");
  const shownBuiltins = builtins.filter((v) => filter === "all" || v.gender === filter);

  const restore = async () => {
    try {
      const res = await api.restoreBuiltin();
      void qc.invalidateQueries({ queryKey: ["voices"] });
      void qc.invalidateQueries({ queryKey: ["builtin-missing"] });
      toast({ tone: "info", title: res ? "Restoring built-in voices" : "Nothing to restore" });
    } catch (e) {
      toast({ tone: "error", title: "Couldn’t restore", body: e instanceof ApiError ? e.message : undefined });
    }
  };

  return (
    <>
      <PageHeader
        title="Voices"
        sub="Make a voice from a few clips of one person, or start with a built-in voice. Play a voice to hear its sample."
        action={<Button variant="primary" onClick={() => setCreating(true)}><Plus size={16} /> New voice</Button>}
      />

      {isLoading && <div className={GRID} aria-label="Loading voices">{[0, 1, 2].map((i) => <div key={i} className="glass h-56 animate-pulse" />)}</div>}
      {isError && (
        <div className="glass p-8 text-center">
          <p className="text-poor">Couldn’t load your voices. Is the backend running?</p>
          <Button className="mt-4" onClick={() => refetch()}>Try again</Button>
        </div>
      )}

      {voices && (
        <>
          <section aria-labelledby="mine-title">
            <h2 id="mine-title" className="mb-4 text-lg font-semibold">Your voices</h2>
            {mine.length === 0 ? (
              <div className="glass">
                <EmptyState
                  title="No voices of your own yet"
                  body="Upload or record 15–60 seconds of someone speaking, with their permission, and Vaani will learn how they sound."
                  action={<Button variant="primary" size="lg" onClick={() => setCreating(true)}><Plus size={16} /> Create a voice</Button>}
                />
              </div>
            ) : (
              <VoiceGrid voices={mine} onNew={() => setCreating(true)} />
            )}
          </section>

          {(builtins.length > 0 || (missing.data?.length ?? 0) > 0) && (
            <section aria-labelledby="builtin-title" className="mt-12">
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <h2 id="builtin-title" className="text-lg font-semibold">Built-in voices</h2>
                <span className="text-sm text-muted">Ready to use, from the XTTS-v2 model. English accent; non-commercial use.</span>
                <div className="ml-auto flex items-center gap-2">
                  <div className="flex rounded-xl border border-line p-1" role="radiogroup" aria-label="Filter built-in voices">
                    {(["all", "female", "male"] as const).map((f) => (
                      <button key={f} type="button" role="radio" aria-checked={filter === f} onClick={() => setFilter(f)}
                        className={`relative rounded-lg px-3 py-1 text-sm capitalize ${filter === f ? "text-ink" : "text-muted"}`}>
                        {filter === f && <motion.span layoutId="builtin-filter" className="absolute inset-0 rounded-lg bg-white/[0.09]" transition={spring.gentle} />}
                        <span className="relative">{f}</span>
                      </button>
                    ))}
                  </div>
                  {(missing.data?.length ?? 0) > 0 && (
                    <Button size="sm" onClick={restore} title={`Missing: ${missing.data?.join(", ")}`}>
                      <RotateCcw size={13} /> Restore {missing.data?.length} built-in
                    </Button>
                  )}
                </div>
              </div>
              <VoiceGrid voices={shownBuiltins} />
            </section>
          )}
        </>
      )}

      <CreateVoiceDialog open={creating} onOpenChange={setCreating} />
    </>
  );
}

function VoiceGrid({ voices, onNew }: { voices: Voice[]; onNew?: () => void }) {
  return (
    <motion.div layout variants={variants.list} initial="hidden" animate="show" className={GRID}>
      <AnimatePresence mode="popLayout">
        {voices.map((v) => <VoiceCard key={v.id} voice={v} />)}
        {onNew && (
          <motion.button
            key="new"
            layout
            type="button"
            variants={variants.fadeUp}
            onClick={onNew}
            whileHover={{ y: -4, transition: spring.gentle }}
            className="flex min-h-56 flex-col items-center justify-center gap-3 rounded-[var(--radius-xl)] border border-dashed border-line text-muted transition-colors hover:border-[var(--color-violet-soft)] hover:text-ink"
          >
            <span className="flex size-11 items-center justify-center rounded-full bg-white/[0.05]"><Plus size={20} /></span>
            <span className="text-sm">New voice</span>
          </motion.button>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
