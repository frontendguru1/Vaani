import { useEffect, useRef, useState } from "react";
import type { JobEvent } from "./api";

export interface JobState {
  latest: JobEvent | null;
  done: boolean;
  failed: boolean;
}

/**
 * Subscribe to /jobs/{id}/events (Server-Sent Events). Every event is passed to `onEvent`
 * so callers can react to specific types (chunk_started, sample_done, …). The browser's
 * EventSource reconnects on its own; the server replays a snapshot on reconnect.
 */
export function useJobEvents(jobId: string | null, onEvent?: (e: JobEvent) => void): JobState {
  const [state, setState] = useState<JobState>({ latest: null, done: false, failed: false });
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    if (!jobId) return;
    setState({ latest: null, done: false, failed: false });
    const es = new EventSource(`/api/v1/jobs/${jobId}/events`);
    const handle = (msg: MessageEvent) => {
      const ev = JSON.parse(msg.data) as JobEvent;
      handler.current?.(ev);
      const finished = ev.status === "succeeded" || ev.status === "failed";
      setState({ latest: ev, done: finished, failed: ev.status === "failed" });
      if (finished) es.close();
    };
    // Named SSE events: listen to every type the backend emits.
    const types = [
      "snapshot", "progress", "sample_started", "sample_done", "quality", "voice_ready",
      "voiceprint", "chunk_started", "chunk_done", "generation_done", "succeeded", "failed",
    ];
    types.forEach((t) => es.addEventListener(t, handle as EventListener));
    // If the stream dies for good (e.g. the job was deleted → 404), EventSource stops
    // retrying silently. Ask once for the job's state so the UI never hangs on "Generating…".
    es.onerror = () => {
      if (es.readyState !== EventSource.CLOSED) return;
      fetch(`/api/v1/jobs/${jobId}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((job: JobEvent) => {
          if (job.status === "queued" || job.status === "running") return; // still alive
          const failed = job.status !== "succeeded";
          const ev = { ...job, type: failed ? "failed" : "succeeded", status: failed ? "failed" : "succeeded", data: {} } as JobEvent;
          if (failed && !ev.error) ev.error = "Lost contact with this job.";
          handler.current?.(ev);
          setState({ latest: ev, done: true, failed });
        })
        .catch(() => {
          const ev = { job_id: jobId, type: "failed", status: "failed", error: "This job no longer exists.", data: {} } as unknown as JobEvent;
          handler.current?.(ev);
          setState({ latest: ev, done: true, failed: true });
        });
    };
    return () => es.close();
  }, [jobId]);

  return state;
}
