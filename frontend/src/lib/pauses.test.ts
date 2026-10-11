import { findPauses, parsePause, pauseLabel } from "./pauses";

test.each([
  ["", 1000], ["1s", 1000], [" 1.5 s ", 1500], ["2", 2000], ["500ms", 500], ["3 seconds", 3000], ["60s", 10000],
])("parsePause(%j) = %d", (arg, ms) => expect(parsePause(arg)).toBe(ms));

test.each(["abc", "1 minute", "-1s"])("parsePause rejects %j", (arg) => expect(parsePause(arg)).toBeNull());

test("findPauses gives positions, durations and flags bad ones", () => {
  const text = "Hi [pause 2s] there [PAUSE] and [pause soon].";
  const p = findPauses(text);
  expect(p.map((x) => x.ms)).toEqual([2000, 1000, null]);
  expect(text.slice(p[0].start, p[0].end)).toBe("[pause 2s]");
});

test("pauseLabel", () => {
  expect(pauseLabel(1000)).toBe("1s");
  expect(pauseLabel(500)).toBe("500ms");
  expect(pauseLabel(1500)).toBe("1.5s");
});
