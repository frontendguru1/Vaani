import { duration, fadeOnly, spring, variants } from "./tokens";

test("interaction durations stay inside the 150–400 ms budget (instant excepted)", () => {
  const { instant, ambient, ...interactive } = duration;
  for (const d of Object.values(interactive)) {
    expect(d).toBeGreaterThanOrEqual(0.15);
    expect(d).toBeLessThanOrEqual(0.4);
  }
  expect(instant).toBeLessThan(0.15);
  expect(ambient).toBeGreaterThan(5);
});

test("fadeOnly strips transforms under reduced motion", () => {
  const reduced = fadeOnly(true, variants.fadeUp);
  expect(reduced.hidden).toEqual({ opacity: 0 });
  expect(JSON.stringify(reduced)).not.toMatch(/"(x|y|scale)"/);
  expect(fadeOnly(false, variants.fadeUp)).toBe(variants.fadeUp);
});

test("springs are springs", () => {
  for (const s of Object.values(spring)) expect(s.type).toBe("spring");
});
