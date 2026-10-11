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
