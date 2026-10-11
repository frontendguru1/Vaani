import { splitBulk, titleFromFile } from "./split";

test("splits on --- lines and reads # titles", () => {
  const items = splitBulk("# Intro\nHello there.\n---\nSecond script\nover two lines.\n  ---  \n\n---\n# Outro\nBye!");
  expect(items.map((i) => [i.title, i.script])).toEqual([
    ["Intro", "Hello there."],
    ["", "Second script\nover two lines."],
    ["Outro", "Bye!"],
  ]);
});

test("a dash inside text is not a separator", () => {
  expect(splitBulk("Well - maybe --- not.")).toHaveLength(1);
});

test("titles from file names", () => {
  expect(titleFromFile("traffic_rules-v2.txt")).toBe("traffic rules v2");
});
