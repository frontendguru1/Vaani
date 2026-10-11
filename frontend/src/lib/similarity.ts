/** Mirrors backend similarity.label(): ECAPA cosine → words. */
export function similarityLabel(score: number | null | undefined): string | null {
  if (score == null) return null;
  if (score >= 0.75) return "very close";
  if (score >= 0.6) return "close";
  if (score >= 0.45) return "somewhat similar";
  return "different";
}

export function similarityColor(score: number): string {
  return score >= 0.75 ? "var(--color-good)" : score >= 0.6 ? "var(--color-cyan)" : score >= 0.45 ? "var(--color-okay)" : "var(--color-poor)";
}
