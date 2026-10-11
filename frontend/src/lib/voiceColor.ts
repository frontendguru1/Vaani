/**
 * Every voice gets its own hue, derived from its id, so the same person is the same colour
 * on their card, their waveform and the generation orb. Hues are kept inside the theme's
 * violet → cyan → pink arc (plus a teal/amber pair) so nothing clashes with the ink.
 */
const HUES = [262, 280, 300, 322, 196, 172, 228, 246, 38];

export function voiceHue(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return HUES[h % HUES.length];
}

export function voiceColors(id: string | null | undefined) {
  const hue = id ? voiceHue(id) : 262;
  return {
    hue,
    solid: `oklch(0.72 0.17 ${hue})`,
    soft: `oklch(0.72 0.17 ${hue} / 0.18)`,
    glow: `oklch(0.72 0.17 ${hue} / 0.45)`,
    gradient: `linear-gradient(135deg, oklch(0.74 0.17 ${hue}), oklch(0.7 0.15 ${(hue + 50) % 360}))`,
  };
}
