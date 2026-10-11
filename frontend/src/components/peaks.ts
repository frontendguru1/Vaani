/** Decode audio and reduce it to `bars` peak values in 0..1. Cached per source. */
const cache = new Map<string, Promise<number[]>>();
let ctx: AudioContext | null = null;

export function computePeaks(samples: Float32Array, bars: number): number[] {
  const out = new Array<number>(bars).fill(0);
  const step = samples.length / bars;
  for (let i = 0; i < bars; i++) {
    const start = Math.floor(i * step);
    const end = Math.min(samples.length, Math.floor((i + 1) * step));
    let peak = 0;
    for (let j = start; j < end; j += 4) peak = Math.max(peak, Math.abs(samples[j]));
    out[i] = peak;
  }
  const max = Math.max(...out, 0.01);
  // Gentle compression so quiet passages still read as speech.
  return out.map((p) => Math.pow(p / max, 0.7));
}

export function peaksFor(source: string | Blob, bars = 72, key?: string): Promise<number[]> {
  const k = `${key ?? (typeof source === "string" ? source : "")}:${bars}`;
  if (typeof source === "string" || key) {
    const hit = cache.get(k);
    if (hit) return hit;
  }
  const p = (async () => {
    const buf = typeof source === "string"
      ? await (await fetch(source)).arrayBuffer()
      : await source.arrayBuffer();
    ctx ??= new AudioContext();
    const audio = await ctx.decodeAudioData(buf);
    return computePeaks(audio.getChannelData(0), bars);
  })();
  if (typeof source === "string" || key) {
    cache.set(k, p);
    p.catch(() => cache.delete(k));
  }
  return p;
}

export function invalidatePeaks(prefix: string) {
  for (const k of cache.keys()) if (k.startsWith(prefix)) cache.delete(k);
}
