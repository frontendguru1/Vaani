import { formatBytes, formatTime, hasDevanagari, relativeDate } from "./format";
import { voiceColors, voiceHue } from "./voiceColor";

test("formatTime", () => {
  expect(formatTime(0)).toBe("0:00");
  expect(formatTime(65.4)).toBe("1:05");
  expect(formatTime(null)).toBe("0:00");
  expect(formatTime(Number.NaN)).toBe("0:00");
});

test("formatBytes", () => {
  expect(formatBytes(512)).toBe("512 B");
  expect(formatBytes(2048)).toBe("2 KB");
  expect(formatBytes(3.5 * 1024 * 1024)).toBe("3.5 MB");
});

test("relativeDate treats server UTC stamps correctly", () => {
  const now = Date.parse("2026-10-11T12:00:00Z");
  expect(relativeDate("2026-10-11T11:59:30Z", now)).toBe("just now");
  expect(relativeDate("2026-10-11T11:46:00+00:00", now)).toBe("14 min ago");
  expect(relativeDate("2026-10-11T07:00:00Z", now)).toBe("5 h ago");
});

test("hasDevanagari", () => {
  expect(hasDevanagari("आज की meeting")).toBe(true);
  expect(hasDevanagari("Hello")).toBe(false);
});

test("voice colour is stable per id and inside the palette", () => {
  expect(voiceHue("01ABC")).toBe(voiceHue("01ABC"));
  const c = voiceColors("01ABC");
  expect(c.solid).toContain(`${c.hue}`);
  expect(voiceColors(null).hue).toBe(262);
});
