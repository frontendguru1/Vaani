import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { AudioLines, Check, FileAudio, Pencil, Trash2, TriangleAlert, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AudioPlayer } from "../../components/AudioPlayer";
import { Button } from "../../components/Button";
import { RatingPill } from "../../components/ScoreRing";
import { useToast } from "../../components/Toasts";
import { api, ApiError, audioUrl, type Voice } from "../../lib/api";
import { LANGUAGE_NAMES, relativeDate } from "../../lib/format";
import { voiceColors } from "../../lib/voiceColor";
import { ClipsDialog } from "./ClipsDialog";
import { spring, transition, variants } from "../../motion/tokens";

function initials(name: string) {
  const words = name.replace(/[^\p{L}\p{N}\s]/gu, " ").trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((w) => Array.from(w)[0].toUpperCase()).join("") || "?";
}

export function VoiceCard({ voice }: { voice: Voice }) {
  const colors = voiceColors(voice.id);
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(voice.name);
  const [clipsOpen, setClipsOpen] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();

  const remove = useMutation({
    mutationFn: () => api.deleteVoice(voice.id),
    onSuccess: (r) => {
      qc.setQueryData<Voice[]>(["voices"], (vs) => vs?.filter((v) => v.id !== voice.id));
      void qc.invalidateQueries({ queryKey: ["generations"] });
      void qc.invalidateQueries({ queryKey: ["builtin-missing"] });
      toast({
        tone: "success",
        title: `Deleted ${voice.name}`,
        body: `${r.files_removed} files and ${r.generations_removed} generations removed from this Mac.`,
      });
    },
    onError: (e) => toast({ tone: "error", title: "Couldn’t delete", body: e instanceof ApiError ? e.message : undefined }),
  });

  const rename = useMutation({
    mutationFn: (name: string) => api.updateVoice(voice.id, { name }),
    onSuccess: () => {
      setEditing(false);
      void qc.invalidateQueries({ queryKey: ["voices"] });
    },
    onError: (e) => toast({ tone: "error", title: "Couldn’t rename", body: e instanceof ApiError ? e.message : undefined }),
  });

  const ready = voice.status === "ready";

  return (
    <motion.article
      layout
      variants={variants.fadeUp}
      exit={{ opacity: 0, scale: 0.9, filter: "blur(4px)", transition: { duration: 0.26 } }}
      whileHover={confirming ? undefined : { y: -4, transition: spring.gentle }}
      className="glass group relative flex flex-col overflow-hidden p-5"
      style={{ ["--voice" as string]: colors.solid }}
    >
      {/* the voice's own colour, faint in the corner */}
      <div aria-hidden className="pointer-events-none absolute -top-16 -right-16 size-48 rounded-full opacity-40 blur-3xl transition-opacity group-hover:opacity-70" style={{ background: colors.soft }} />

      <div className="relative flex items-start gap-3">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl text-sm font-semibold text-white" style={{ background: colors.gradient, boxShadow: `0 8px 24px -8px ${colors.glow}` }}>
          {initials(voice.name)}
        </div>
        <div className="min-w-0 flex-1">
          {editing ? (
            <form
              className="flex items-center gap-1"
              onSubmit={(e) => {
                e.preventDefault();
                if (draft.trim()) rename.mutate(draft.trim());
              }}
            >
              <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={120} aria-label="Voice name"
                className="field !py-1 text-sm" onKeyDown={(e) => e.key === "Escape" && setEditing(false)} />
              <button type="submit" aria-label="Save name" className="rounded-full p-1.5 text-good hover:bg-white/[0.06]"><Check size={15} /></button>
              <button type="button" aria-label="Cancel rename" onClick={() => setEditing(false)} className="rounded-full p-1.5 text-faint hover:bg-white/[0.06]"><X size={15} /></button>
            </form>
          ) : (
            <h3 className="truncate text-base font-semibold">{voice.name}</h3>
          )}
          <p className="mt-0.5 text-xs text-muted">
            {voice.source === "builtin" ? (
              <>Built-in {voice.gender ?? ""} voice</>
            ) : (
              <>
                <span lang={voice.language === "hi" ? "hi" : undefined}>{LANGUAGE_NAMES[voice.language] ?? voice.language}</span>
                {ready && <>, {Math.round(voice.speech_seconds)}s of speech</>}
              </>
            )}
          </p>
        </div>
        {voice.source === "builtin" ? (
          <span className="rounded-full border border-line px-2 py-0.5 text-[11px] text-muted">Built-in</span>
        ) : (
          ready && voice.quality_rating && <RatingPill rating={voice.quality_rating} />
        )}
      </div>

      {voice.description && <p className="relative mt-3 line-clamp-2 text-sm text-muted">{voice.description}</p>}

      <div className="relative mt-4 min-h-[44px]">
        {ready && voice.has_preview ? (
          <AudioPlayer src={audioUrl.preview(voice.id)} color={colors.solid} compact />
        ) : voice.status === "processing" ? (
          <div className="flex items-center gap-2 text-sm text-muted">
            <motion.span className="size-2 rounded-full" style={{ background: colors.solid }} animate={{ scale: [1, 1.6, 1] }} transition={{ duration: 1, repeat: Infinity }} />
            Processing…
          </div>
        ) : voice.status === "failed" ? (
          <p className="flex items-start gap-2 text-xs text-poor"><TriangleAlert size={14} className="mt-0.5 shrink-0" />{voice.error ?? "Processing failed."}</p>
        ) : null}
      </div>

      <div className="relative mt-5 flex items-center gap-1 border-t border-line pt-4">
        <AnimatePresence mode="wait" initial={false}>
          {confirming ? (
            <motion.div key="confirm" className="flex w-full flex-wrap items-center gap-2" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0, transition: transition.enter }} exit={{ opacity: 0, y: -6 }}>
              <p className="mr-auto text-xs text-muted">
                Delete {voice.name} and {voice.generation_count === 1 ? "its 1 generation" : `its ${voice.generation_count} generations`}? This can’t be undone.
              </p>
              <Button size="sm" variant="quiet" onClick={() => setConfirming(false)}>Keep</Button>
              <Button size="sm" variant="danger" onClick={() => remove.mutate()} disabled={remove.isPending} autoFocus>
                {remove.isPending ? "Deleting…" : "Delete"}
              </Button>
            </motion.div>
          ) : (
            <motion.div key="actions" className="flex w-full items-center gap-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <Button size="sm" variant="ghost" disabled={!ready} onClick={() => navigate(`/generate?voice=${voice.id}`)}>
                <AudioLines size={14} /> Generate
              </Button>
              <Button size="sm" variant="quiet" disabled={!ready} onClick={() => setClipsOpen(true)} aria-label={`Clips and transcripts for ${voice.name}`}>
                <FileAudio size={14} /> Clips
              </Button>
              <span className="ml-auto whitespace-nowrap text-xs text-faint">{relativeDate(voice.created_at)}</span>
              <Button size="sm" variant="quiet" aria-label={`Rename ${voice.name}`} onClick={() => { setDraft(voice.name); setEditing(true); }}>
                <Pencil size={14} />
              </Button>
              <Button size="sm" variant="quiet" aria-label={`Delete ${voice.name}`} onClick={() => setConfirming(true)}>
                <Trash2 size={14} />
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      {ready && <ClipsDialog voice={voice} open={clipsOpen} onOpenChange={setClipsOpen} />}
    </motion.article>
  );
}
