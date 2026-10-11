import { render, screen } from "@testing-library/react";
import { RatingPill, ScoreRing } from "./ScoreRing";

test("score ring announces rating and score", () => {
  render(<ScoreRing score={84} rating="good" />);
  expect(screen.getByLabelText("Quality Good, score 84 of 100")).toBeInTheDocument();
});

test("rating pill label", () => {
  render(<RatingPill rating="poor" />);
  expect(screen.getByText("Poor")).toBeInTheDocument();
});
