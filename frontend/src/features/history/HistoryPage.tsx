import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/AppShell";
import { AudioPlayer } from "../../components/AudioPlayer";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toasts";
import { api, ApiError, audioUrl, type Generation } from "../../lib/api";
import { formatTime, hasDevanagari, relativeDate } from "../../lib/format";
import { voiceColors } from "../../lib/voiceColor";
import { similarityColor, similarityLabel } from "../../lib/similarity";
import { transition, variants } from "../../motion/tokens";

export function HistoryPage() {
  const qc = useQueryClient();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["generations"],
    queryFn: () => api.generations(),
    refetchInterval: (q) => (q.state.data?.some((g) => g.status === "queued" || g.status === "running") ? 2000 : false),
  });
  const navigate = useNavigate();

  return (
    <>
      <PageHeader title="History" sub="Everything you’ve generated, newest first. Files stay on this Mac until you delete them." />
      {isLoading && <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="glass h-36 animate-pulse" />)}</div>}
      {isError && (
        <div className="glass p-8 text-center">
          <p className="text-poor">Couldn’t load history.</p>
          <Button className="mt-4" onClick={() => refetch()}>Try again</Button>
        </div>
      )}
      {data && data.length === 0 && (
        <div className="glass">
          <EmptyState title="Nothing generated yet" body="Your generated audio will show up here, ready to play again or download."
            action={<Button variant="primary" onClick={() => navigate("/generate")}>Generate something</Button>} />
        </div>
      )}
      {data && data.length > 0 && (
        <motion.ul variants={variants.list} initial="hidden" animate="show" className="space-y-3">
          <AnimatePresence mode="popLayout">
            {data.map((g) => <HistoryItem key={g.id} gen={g} onChanged={() => qc.invalidateQueries({ queryKey: ["generations"] })} />)}
          </AnimatePresence>
        </motion.ul>
      )}
    </>
  );
}

function HistoryItem({ gen, onChanged }: { gen: Generation; onChanged: () => void }) {
  const colors = voiceColors(gen.voice_id);
  const [confirming, setConfirming] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  const remove = useMutation({
    mutationFn: () => api.deleteGeneration(gen.id),
    onSuccess: () => {
      onChanged();
      toast({ tone: "success", title: "Deleted from history" });
    },
    onError: (e) => toast({ tone: "error", title: "Couldn’t delete", body: e instanceof ApiError ? e.message : undefined }),
  });
  const regenerate = useMutation({
    mutationFn: () => api.regenerate(gen.id),
    onSuccess: () => {
      onChanged();
      toast({ tone: "info", title: "Regenerating", body: "The new version will appear at the top." });
    },
    onError: (e) => toast({ tone: "error", title: "Couldn’t regenerate", body: e instanceof ApiError ? e.message : undefined }),
  });

  return (
    <motion.li layout variants={variants.fadeUp} exit={{ opacity: 0, x: -30, transition: transition.exit }} className="glass relative overflow-hidden p-5">
      <span aria-hidden className="absolute inset-y-0 left-0 w-1" style={{ background: colors.gradient }} />
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-sm font-medium" style={{ color: colors.solid }}>
          {gen.speakers.length > 1 ? `Dialogue: ${gen.speakers.join(", ")}` : (gen.speakers[0] ?? gen.voice_name ?? "Deleted voice")}
        </p>
        <p className="text-xs text-faint">
          {relativeDate(gen.created_at)}
          {gen.status === "done" && gen.compute_seconds != null && <>, made in {gen.compute_seconds.toFixed(1)}s</>}
          {gen.similarity != null && (
            <span className="ml-2 inline-flex items-center gap-1" title={`Sounds ${similarityLabel(gen.similarity)} to the voice`}>
              <span className="size-1.5 rounded-full" style={{ background: similarityColor(gen.similarity) }} />
              <span className="font-mono">{Math.round(Math.max(0, gen.similarity) * 100)}%</span> match
            </span>
          )}
        </p>
      </div>
      <p lang={hasDevanagari(gen.script) ? "hi" : undefined} className="mt-2 line-clamp-2 max-w-[75ch] text-[15px] leading-relaxed text-ink/90">
        {gen.script}
      </p>

      <div className="mt-4">
        {gen.status === "done" ? (
          <AudioPlayer src={audioUrl.generation(gen.id)} color={colors.solid} compact
            downloads={[
              { label: "WAV", href: audioUrl.generation(gen.id, "wav", true) },
              { label: "MP3", href: audioUrl.generation(gen.id, "mp3", true) },
              { label: "SRT", href: audioUrl.subtitles(gen.id, "srt"), title: "Subtitles (SRT)" },
            ]} />
        ) : gen.status === "failed" ? (
          <p className="text-xs text-poor">Failed: {gen.error}</p>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted">
            <motion.span className="size-2 rounded-full" style={{ background: colors.solid }} animate={{ scale: [1, 1.6, 1] }} transition={{ duration: 1, repeat: Infinity }} />
            {gen.status === "queued" ? "Waiting in the queue…" : "Generating…"}
          </p>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <AnimatePresence mode="wait" initial={false}>
          {confirming ? (
            <motion.div key="c" className="flex flex-wrap items-center gap-2" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <span className="text-xs text-muted">Delete this audio?</span>
              <Button size="sm" variant="quiet" onClick={() => setConfirming(false)}>Keep</Button>
              <Button size="sm" variant="danger" autoFocus onClick={() => remove.mutate()} disabled={remove.isPending}>Delete</Button>
            </motion.div>
          ) : (
            <motion.div key="a" className="flex flex-wrap items-center gap-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <Button size="sm" variant="ghost" onClick={() => regenerate.mutate()} disabled={regenerate.isPending || gen.status === "running" || !gen.voice_name}>
                <RotateCcw size={13} /> Regenerate
              </Button>
              <Button size="sm" variant="quiet" onClick={() => navigate(`/generate?voice=${gen.voice_id}`)} disabled={!gen.voice_name}>
                Use this voice
              </Button>
              <span className="mx-2 font-mono text-xs text-faint">
                {gen.duration_seconds != null && formatTime(gen.duration_seconds)}
              </span>
              <Button size="sm" variant="quiet" aria-label="Delete" onClick={() => setConfirming(true)} disabled={gen.status === "running" || gen.status === "queued"}>
                <Trash2 size={14} />
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.li>
  );
}
