import { findSpeakerTags } from "./dialogue";

const voices = [{ id: "v1", name: "Papa" }, { id: "v2", name: "Dadi Ji" }];

test("finds line-start tags, matches names loosely, flags unknown", () => {
  const text = "Intro.\n[Papa]: Hi\n[ dadi  ji ]:Hello\n[Ravi]: ?\nNot [Papa]: a tag";
  const tags = findSpeakerTags(text, voices);
  expect(tags.map((t) => [t.name, t.voiceId])).toEqual([["Papa", "v1"], ["dadi  ji", "v2"], ["Ravi", null]]);
  expect(text.slice(tags[0].start, tags[0].end)).toBe("[Papa]: ");
});

test("pause markers are not speakers", () => {
  expect(findSpeakerTags("[pause 1s]: wow", voices)).toEqual([]);
});
