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
    return () => es.close();
  }, [jobId]);

  return state;
}
