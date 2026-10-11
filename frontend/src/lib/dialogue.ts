/** Mirrors backend/app/services/dialogue.py: "[Name]: text" at a line start hands the line
 * to that voice. Used for live chips and validation in the editor. */

export interface SpeakerTag {
  start: number; // span of the whole tag, e.g. "[Papa]: "
  end: number;
  name: string;
  voiceId: string | null; // null = no voice with that name
}

const TAG = /^[ \t]*\[([^[\]\n]{1,120})\][ \t]*:[ \t]*/gm;
export const normName = (n: string) => n.split(/\s+/).filter(Boolean).join(" ").toLocaleLowerCase();

export function findSpeakerTags(text: string, voices: { id: string; name: string }[]): SpeakerTag[] {
  const byName = new Map<string, string>();
  for (const v of voices) if (!byName.has(normName(v.name))) byName.set(normName(v.name), v.id);
  const out: SpeakerTag[] = [];
  for (const m of text.matchAll(TAG)) {
    const name = m[1].trim();
    if (normName(name).startsWith("pause")) continue; // "[pause 1s]:" is a pause, not a speaker
    out.push({ start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, name, voiceId: byName.get(normName(name)) ?? null });
  }
  return out;
}
