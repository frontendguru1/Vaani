import { motion, useReducedMotion } from "motion/react";
import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { spring } from "../../motion/tokens";

export const ACCEPT = ".wav,.mp3,.m4a,.ogg,.webm,.flac,.aac,.aiff,.aif,.opus,audio/*";

export function Dropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const reduced = useReducedMotion();
  const depth = useRef(0);

  return (
    <motion.div
      onDragEnter={(e) => {
        e.preventDefault();
        depth.current += 1;
        setOver(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        depth.current -= 1;
        if (depth.current <= 0) setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        onFiles(Array.from(e.dataTransfer.files));
      }}
      animate={{ scale: over && !reduced ? 1.015 : 1 }}
      transition={spring.gentle}
      className="relative"
    >
      <button
        type="button"
        onClick={() => input.current?.click()}
        className="relative flex w-full flex-col items-center justify-center gap-2 overflow-hidden rounded-2xl border border-dashed px-6 py-8 text-center transition-colors"
        style={{
          borderColor: over ? "var(--color-violet-soft)" : "var(--color-border-strong)",
          background: over ? "rgb(139 92 246 / 0.1)" : "rgb(255 255 255 / 0.02)",
          boxShadow: over ? "0 0 0 4px rgb(139 92 246 / .15), 0 0 40px -6px rgb(139 92 246 / .5)" : "none",
        }}
      >
        <motion.span
          animate={over && !reduced ? { y: [-2, -8, -2] } : { y: 0 }}
          transition={over ? { duration: 1, repeat: Infinity, ease: "easeInOut" } : spring.gentle}
          className="flex size-11 items-center justify-center rounded-full bg-white/[0.06] text-violet-soft"
        >
          <Upload size={20} />
        </motion.span>
        <span className="text-sm font-medium">{over ? "Drop to add" : "Drop audio files here, or choose files"}</span>
        <span className="text-xs text-faint">WAV, MP3, M4A or OGG · 15–60 seconds of clean speech in total works best</span>
      </button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          onFiles(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </motion.div>
  );
}
