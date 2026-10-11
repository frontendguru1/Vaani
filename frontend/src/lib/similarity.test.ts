import { similarityLabel } from "./similarity";

test("labels mirror the backend thresholds", () => {
  expect(similarityLabel(0.84)).toBe("very close");
  expect(similarityLabel(0.65)).toBe("close");
  expect(similarityLabel(0.5)).toBe("somewhat similar");
  expect(similarityLabel(0.1)).toBe("different");
  expect(similarityLabel(null)).toBeNull();
});
