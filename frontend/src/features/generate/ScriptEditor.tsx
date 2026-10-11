import { useLayoutEffect, useRef } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  /** [start, end) char span to highlight (the sentence being generated or played). */
  highlight: [number, number] | null;
  readOnly?: boolean;
  color: string;
}

/**
 * A textarea with a mirrored backdrop so a span of the text can be highlighted in place.
 * Both layers share font, padding and wrapping; the backdrop scrolls with the textarea.
 */
export function ScriptEditor({ value, onChange, highlight, readOnly, color }: Props) {
  const area = useRef<HTMLTextAreaElement>(null);
  const backdrop = useRef<HTMLDivElement>(null);
  const mark = useRef<HTMLElement>(null);

  // Keep the highlighted sentence in view while generating.
  useLayoutEffect(() => {
    const a = area.current;
    const m = mark.current;
    if (!a || !m || !highlight) return;
    const top = m.offsetTop - a.clientHeight / 3;
    a.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }, [highlight]);

  const shared = "whitespace-pre-wrap break-words px-5 py-4 text-[17px] leading-[1.75]";
  const before = highlight ? value.slice(0, highlight[0]) : value;
  const mid = highlight ? value.slice(highlight[0], highlight[1]) : "";
  const after = highlight ? value.slice(highlight[1]) : "";

  return (
    <div className="relative">
      <div
        ref={backdrop}
        aria-hidden
        className={`${shared} pointer-events-none absolute inset-0 overflow-hidden text-transparent`}
      >
        {before}
        {highlight && (
          <mark
            ref={mark}
            className="rounded-md text-transparent transition-all duration-300"
            style={{ background: `color-mix(in oklch, ${color} 26%, transparent)`, boxShadow: `0 0 0 3px color-mix(in oklch, ${color} 26%, transparent)` }}
          >
            {mid}
          </mark>
        )}
        {after + "\n"}
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
        placeholder={"Type or paste what the voice should say.\n\nHindi, English or a mix both work, e.g. आज की meeting बहुत अच्छी रही।"}
        className={`${shared} relative block h-[38dvh] min-h-52 w-full lg:h-[min(56dvh,520px)] lg:min-h-64 resize-none rounded-2xl border border-line bg-transparent text-ink outline-none placeholder:text-faint focus-visible:border-[var(--color-violet-soft)] focus-visible:shadow-[0_0_0_3px_rgb(167_139_250/0.25)] ${readOnly ? "cursor-default" : ""}`}
      />
    </div>
  );
}
