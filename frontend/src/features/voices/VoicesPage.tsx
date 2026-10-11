import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { Plus } from "lucide-react";
import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { api } from "../../lib/api";
import { spring, variants } from "../../motion/tokens";
import { CreateVoiceDialog } from "./CreateVoiceDialog";
import { VoiceCard } from "./VoiceCard";

export function VoicesPage() {
  const [creating, setCreating] = useState(false);
  const { data: voices, isLoading, isError, refetch } = useQuery({
    queryKey: ["voices"],
    queryFn: api.voices,
    // Keep polling while something is still processing in the background.
    refetchInterval: (q) => (q.state.data?.some((v) => v.status === "processing") ? 2000 : false),
  });

  return (
    <>
      <PageHeader
        title="Voices"
        sub="Each voice is made from a few clips of one person. Play a voice to hear the clip it was built from."
        action={voices && voices.length > 0 && (
          <Button variant="primary" onClick={() => setCreating(true)}>
            <Plus size={16} /> New voice
          </Button>
        )}
      />

      {isLoading && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(290px,1fr))] gap-5" aria-label="Loading voices">
          {[0, 1, 2].map((i) => <div key={i} className="glass h-56 animate-pulse" />)}
        </div>
      )}

      {isError && (
        <div className="glass p-8 text-center">
          <p className="text-poor">Couldn’t load your voices. Is the backend running?</p>
          <Button className="mt-4" onClick={() => refetch()}>Try again</Button>
        </div>
      )}

      {voices && voices.length === 0 && (
        <div className="glass">
          <EmptyState
            title="No voices yet"
            body="Upload or record 15–60 seconds of someone speaking, with their permission, and Vaani will learn how they sound."
            action={<Button variant="primary" size="lg" onClick={() => setCreating(true)}><Plus size={16} /> Create your first voice</Button>}
          />
        </div>
      )}

      {voices && voices.length > 0 && (
        <motion.div layout variants={variants.list} initial="hidden" animate="show" className="grid grid-cols-[repeat(auto-fill,minmax(290px,1fr))] gap-5">
          <AnimatePresence mode="popLayout">
            {voices.map((v) => <VoiceCard key={v.id} voice={v} />)}
            <motion.button
              key="new"
              layout
              type="button"
              variants={variants.fadeUp}
              onClick={() => setCreating(true)}
              whileHover={{ y: -4, transition: spring.gentle }}
              className="flex min-h-56 flex-col items-center justify-center gap-3 rounded-[var(--radius-xl)] border border-dashed border-line text-muted transition-colors hover:border-[var(--color-violet-soft)] hover:text-ink"
            >
              <span className="flex size-11 items-center justify-center rounded-full bg-white/[0.05]"><Plus size={20} /></span>
              <span className="text-sm">New voice</span>
            </motion.button>
          </AnimatePresence>
        </motion.div>
      )}

      <CreateVoiceDialog open={creating} onOpenChange={setCreating} />
    </>
  );
}
