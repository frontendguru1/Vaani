import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, type ReactNode } from "react";
import { findPauses } from "../../lib/pauses";

interface Props {
  value: string;
  onChange: (v: string) => void;
  /** [start, end) char span to highlight (the sentence being generated or played). */
  highlight: [number, number] | null;
  readOnly?: boolean;
  color: string;
  /** Extra spans to draw as chips, e.g. dialogue speaker tags (color null = problem). */
  decorations?: { start: number; end: number; color: string | null }[];
}

export interface ScriptEditorHandle {
  /** Insert text at the caret (or replace the selection) and keep focus. */
  insert: (text: string) => void;
  /** Start a new line at the caret's line end and insert text there (for speaker tags). */
  insertLine: (text: string) => void;
}

/**
 * A textarea with a mirrored backdrop, so parts of the text can be styled in place:
 * the sentence being generated/played is highlighted, and [pause …] markers show as chips
 * (red if they can't be read). Both layers share font, padding and wrapping; the backdrop
 * scrolls with the textarea.
 */
export const ScriptEditor = forwardRef<ScriptEditorHandle, Props>(function ScriptEditor(
  { value, onChange, highlight, readOnly, color, decorations = [] },
  ref,
) {
  const area = useRef<HTMLTextAreaElement>(null);
  const backdrop = useRef<HTMLDivElement>(null);
  const mark = useRef<HTMLElement>(null);
  // Caret to restore after an insert. Applied in a layout effect, i.e. synchronously right
  // after React commits the new text and before any further keystrokes are handled — a
  // requestAnimationFrame here let fast typing land in the wrong place.
  const pendingCaret = useRef<number | null>(null);
  useLayoutEffect(() => {
    const a = area.current;
    if (a && pendingCaret.current != null) {
      a.focus();
      a.setSelectionRange(pendingCaret.current, pendingCaret.current);
      pendingCaret.current = null;
    }
  }, [value]);

  useImperativeHandle(ref, () => ({
    insertLine(text: string) {
      const a = area.current;
      if (!a) return;
      const caret = a.selectionEnd ?? value.length;
      const lineEnd = value.indexOf("\n", caret);
      const at = lineEnd === -1 ? value.length : lineEnd;
      const before = value.slice(0, at);
      const prefix = before.trim() ? "\n" : "";
      const next = before + prefix + text + value.slice(at);
      pendingCaret.current = (before + prefix + text).length;
      onChange(next);
    },
    insert(text: string) {
      const a = area.current;
      if (!a) return;
      const start = a.selectionStart ?? value.length;
      const end = a.selectionEnd ?? value.length;
      const before = value.slice(0, start);
      const pad = before && !/\s$/.test(before) ? " " : "";
      const after = value.slice(end);
      const tail = after && !/^\s/.test(after) ? " " : "";
      const next = before + pad + text + tail + after;
      pendingCaret.current = (before + pad + text + tail).length;
      onChange(next);
    },
  }));

  // Keep the highlighted sentence in view while generating.
  useLayoutEffect(() => {
    const a = area.current;
    const m = mark.current;
    if (!a || !m || !highlight) return;
    a.scrollTo({ top: Math.max(0, m.offsetTop - a.clientHeight / 3), behavior: "smooth" });
  }, [highlight]);

  const shared = "whitespace-pre-wrap break-words px-5 py-4 text-[17px] leading-[1.75]";

  // Build backdrop pieces: plain text, pause chips, and the highlight span.
  const cuts = new Set<number>([0, value.length]);
  const pauses = findPauses(value);
  pauses.forEach((p) => { cuts.add(p.start); cuts.add(p.end); });
  decorations.forEach((d) => { cuts.add(d.start); cuts.add(d.end); });
  if (highlight) { cuts.add(highlight[0]); cuts.add(highlight[1]); }
  const points = [...cuts].filter((n) => n >= 0 && n <= value.length).sort((a, b) => a - b);
  const pieces: ReactNode[] = [];
  let markPlaced = false;
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]];
    if (a === b) continue;
    const text = value.slice(a, b);
    const pause = pauses.find((p) => a >= p.start && b <= p.end);
    const deco = decorations.find((d) => a >= d.start && b <= d.end);
    const lit = highlight && a >= highlight[0] && b <= highlight[1];
    if (deco) {
      const c = deco.color;
      pieces.push(
        <span key={a} className="rounded-md text-transparent"
          style={{ background: c ? `color-mix(in oklch, ${c} 24%, transparent)` : "rgb(248 113 113 / .22)", boxShadow: `0 0 0 1px ${c ? `color-mix(in oklch, ${c} 55%, transparent)` : "rgb(248 113 113 / .5)"}` }}>
          {text}
        </span>,
      );
    } else if (pause) {
      pieces.push(
        <span key={a} className="rounded-md text-transparent"
          style={{ background: pause.ms == null ? "rgb(248 113 113 / .22)" : "rgb(34 211 238 / .16)", boxShadow: `0 0 0 1px ${pause.ms == null ? "rgb(248 113 113 / .5)" : "rgb(34 211 238 / .35)"}` }}>
          {text}
        </span>,
      );
    } else if (lit) {
      pieces.push(
        <mark key={a} ref={markPlaced ? undefined : mark} className="rounded-md text-transparent transition-all duration-300"
          style={{ background: `color-mix(in oklch, ${color} 26%, transparent)`, boxShadow: `0 0 0 3px color-mix(in oklch, ${color} 26%, transparent)` }}>
          {text}
        </mark>,
      );
      markPlaced = true;
    } else {
      pieces.push(text);
    }
  }

  return (
    <div className="relative">
      <div ref={backdrop} aria-hidden className={`${shared} pointer-events-none absolute inset-0 overflow-hidden text-transparent`}>
        {pieces}
        {"\n"}
      </div>
      <textarea
        ref={area}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={(e) => {
          if (backdrop.current) backdrop.current.scrollTop = e.currentTarget.scrollTop;
        }}
        readOnly={readOnly}
        aria-label="Script"
        placeholder={"Type or paste what the voice should say.\n\nHindi, English or a mix both work, e.g. आज की meeting बहुत अच्छी रही।\nAdd [pause 1s] anywhere for a longer break.\nFor a dialogue, start lines with a voice name: [Papa]: …"}
        className={`${shared} relative block h-[38dvh] min-h-52 w-full resize-none rounded-2xl border border-line bg-transparent text-ink outline-none placeholder:text-faint focus-visible:border-[var(--color-violet-soft)] focus-visible:shadow-[0_0_0_3px_rgb(167_139_250/0.25)] lg:h-[min(56dvh,520px)] lg:min-h-64 ${readOnly ? "cursor-default" : ""}`}
      />
    </div>
  );
});
