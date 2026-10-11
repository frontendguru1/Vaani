import { computePeaks } from "./peaks";

test("peaks are normalised to 0..1 with one value per bar", () => {
  const s = new Float32Array(1000);
  for (let i = 0; i < 1000; i++) s[i] = i < 500 ? 0.1 : 0.5;
  const p = computePeaks(s, 10);
  expect(p).toHaveLength(10);
  expect(Math.max(...p)).toBeCloseTo(1);
  expect(p[0]).toBeLessThan(p[9]);
});

test("silence does not divide by zero", () => {
  const p = computePeaks(new Float32Array(100), 5);
  expect(p.every((v) => Number.isFinite(v))).toBe(true);
});
