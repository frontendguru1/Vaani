/** Mirrors backend/app/services/chunking.py pause-marker parsing, for live editor feedback. */

export interface PauseMarker {
  start: number;
  end: number;
  ms: number | null; // null = couldn't read it
  raw: string;
}

const MARKER = /\[\s*pause\b([^\]]*)\]/gi;
const DURATION = /^\s*(\d+(?:\.\d+)?)\s*(ms|milliseconds?|s|secs?|seconds?)?\s*$/i;
export const MAX_PAUSE_MS = 10_000;

export function parsePause(arg: string): number | null {
  if (!arg.trim()) return 1000;
  const m = DURATION.exec(arg);
  if (!m) return null;
  const value = Number(m[1]);
  const unit = (m[2] ?? "s").toLowerCase();
  return Math.min(MAX_PAUSE_MS, Math.round(unit.startsWith("m") ? value : value * 1000));
}

export function findPauses(text: string): PauseMarker[] {
  return Array.from(text.matchAll(MARKER), (m) => ({
    start: m.index ?? 0,
    end: (m.index ?? 0) + m[0].length,
    ms: parsePause(m[1]),
    raw: m[0],
  }));
}

export function pauseLabel(ms: number): string {
  return ms % 1000 === 0 ? `${ms / 1000}s` : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}
