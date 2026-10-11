import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { ToastProvider } from "../../components/Toasts";
import { PronunciationPage } from "./PronunciationPage";

/** Regression: the Try-it preview kept showing the pre-change text after adding an entry. */
test("adding an entry refreshes the Try-it preview", async () => {
  let entries: { id: string; term: string; replacement: string; language: null; case_sensitive: boolean }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/pronunciations") && init?.method === "POST") {
      const b = JSON.parse(String(init.body));
      entries = [{ id: "1", ...b, language: null }];
      return new Response(JSON.stringify(entries[0]), { status: 201 });
    }
    if (url.endsWith("/pronunciations")) return new Response(JSON.stringify(entries));
    if (url.endsWith("/pronunciations/preview")) {
      const { text } = JSON.parse(String(init?.body));
      const out = entries.length ? text.replace("Vaani", "Vaa-nee") : text;
      return new Response(JSON.stringify({ text: out, applied: entries.length ? [{ term: "Vaani", replacement: "Vaa-nee", count: 1 }] : [] }));
    }
    return new Response("{}", { status: 404 });
  });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ToastProvider><PronunciationPage /></ToastProvider>
    </QueryClientProvider>,
  );
  await screen.findByText("No fixes yet");
  fireEvent.change(screen.getByPlaceholderText("Vaani"), { target: { value: "Vaani" } });
  fireEvent.change(screen.getByPlaceholderText("Vaa-nee"), { target: { value: "Vaa-nee" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(screen.getByText(/Welcome to Vaa-nee!/)).toBeInTheDocument(), { timeout: 3000 });
});
