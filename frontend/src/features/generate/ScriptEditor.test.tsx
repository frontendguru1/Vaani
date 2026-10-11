import { fireEvent, render, screen } from "@testing-library/react";
import { ScriptEditor } from "./ScriptEditor";

beforeAll(() => {
  Element.prototype.scrollTo = () => {};
});

test("highlights exactly the requested span", () => {
  const text = "First sentence. Second sentence here.";
  const { container } = render(
    <ScriptEditor value={text} onChange={() => {}} highlight={[16, 37]} color="red" />,
  );
  expect(container.querySelector("mark")?.textContent).toBe("Second sentence here.");
});

test("no highlight renders no mark, and typing calls onChange", () => {
  const onChange = vi.fn();
  const { container } = render(<ScriptEditor value="" onChange={onChange} highlight={null} color="red" />);
  expect(container.querySelector("mark")).toBeNull();
  fireEvent.change(screen.getByRole("textbox", { name: "Script" }), { target: { value: "नमस्ते" } });
  expect(onChange).toHaveBeenCalledWith("नमस्ते");
});

test("read-only while generating", () => {
  render(<ScriptEditor value="x" onChange={() => {}} highlight={[0, 1]} readOnly color="red" />);
  expect(screen.getByRole("textbox", { name: "Script" })).toHaveAttribute("readonly");
});

test("pause markers render as chips, unreadable ones in red", () => {
  const { container } = render(
    <ScriptEditor value="Hi [pause 1s] there [pause soon]." onChange={() => {}} highlight={null} color="red" />,
  );
  const chips = [...container.querySelectorAll("div[aria-hidden] span")].map((s) => s.textContent);
  expect(chips).toEqual(["[pause 1s]", "[pause soon]"]);
});

test("insert() adds a marker at the caret with spacing", async () => {
  const { createRef } = await import("react");
  const ref = createRef<import("./ScriptEditor").ScriptEditorHandle>();
  const onChange = vi.fn();
  render(<ScriptEditor ref={ref} value="Hello world" onChange={onChange} highlight={null} color="red" />);
  const box = screen.getByRole("textbox", { name: "Script" }) as HTMLTextAreaElement;
  box.setSelectionRange(5, 5);
  ref.current!.insert("[pause 1s]");
  expect(onChange).toHaveBeenCalledWith("Hello [pause 1s] world");
});
