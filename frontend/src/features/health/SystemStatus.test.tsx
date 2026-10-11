import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { SystemStatus } from "./SystemStatus";
import type { Health } from "./api";

const healthy: Health = {
  status: "ok",
  app: "vaani",
  version: "0.1.0",
  database: true,
  ffmpeg: { available: true, version: "9.0.2" },
  device: { torch_installed: false, torch_version: null, mps_available: false, preferred: "cpu" },
};

function mockFetch(impl: () => Promise<Response>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(impl);
}

test("renders each subsystem from the real health payload", async () => {
  const spy = mockFetch(async () => new Response(JSON.stringify(healthy)));
  render(<SystemStatus />);
  expect(screen.getByLabelText("Loading system status")).toBeInTheDocument();
  expect(await screen.findByText("9.0.2")).toBeInTheDocument();
  expect(screen.getByText("SQLite · migrated")).toBeInTheDocument();
  expect(screen.getByText("torch not installed yet")).toBeInTheDocument();
  expect(screen.getByText("ready")).toBeInTheDocument();
  expect(spy).toHaveBeenCalledWith("/api/v1/health", undefined);
});

test("shows degraded when ffmpeg is missing", async () => {
  const payload = { ...healthy, status: "degraded", ffmpeg: { available: false, version: null } };
  mockFetch(async () => new Response(JSON.stringify(payload)));
  render(<SystemStatus />);
  expect(await screen.findByText("missing")).toBeInTheDocument();
  expect(screen.getByText("degraded")).toBeInTheDocument();
});

test("shows an offline message when the backend is down", async () => {
  mockFetch(async () => new Response("", { status: 502, statusText: "Bad Gateway" }));
  render(<SystemStatus />);
  expect(await screen.findByText(/Can’t reach the backend/)).toBeInTheDocument();
  expect(screen.getByText("offline")).toBeInTheDocument();
});
