/** Typed client for /api/v1. Feature modules build on `request`/`upload`. */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
  }
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const detail = typeof body.detail === "string" ? body.detail : res.statusText;
    return new ApiError(res.status, detail, body.code);
  } catch {
    return new ApiError(res.status, `${res.status} ${res.statusText}`);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, init);
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/**
 * Multipart upload with real progress (fetch can't report upload progress, XHR can).
 * `onProgress` gets 0..1 of bytes sent.
 */
export function upload<T>(
  path: string,
  form: FormData,
  onProgress?: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/v1${path}`);
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(1);
        resolve(xhr.response as T);
      } else {
        const body = xhr.response ?? {};
        reject(new ApiError(xhr.status, body.detail ?? `Upload failed (${xhr.status})`, body.code));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Can’t reach the backend."));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(form);
  });
}

// ---- Shared types (mirror backend schemas) ----

export type Rating = "good" | "okay" | "poor";

export interface QualityIssue {
  severity: "okay" | "poor";
  code: string;
  message: string;
}

export interface QualityReport {
  rating: Rating;
  score: number;
  duration: number;
  speech_seconds: number;
  silence_ratio: number;
  snr_db: number | null;
  clipping_ratio: number;
  pitch_spread: number | null;
  issues: QualityIssue[];
}

export interface VoiceSummaryReport {
  rating: Rating;
  score: number;
  speech_seconds: number;
  sample_ratings: Rating[];
  issues: QualityIssue[];
}

export interface Sample {
  id: string;
  kind: "upload" | "recording" | "builtin";
  original_filename: string;
  size_bytes: number;
  duration_seconds: number;
  transcript: string | null;
  transcript_source: "user" | "whisper" | "builtin" | null;
  transcript_segments: { start: number; end: number; text: string }[] | null;
  quality: QualityReport | null;
  has_audio: boolean;
}

export interface Voice {
  id: string;
  name: string;
  language: string;
  description: string;
  consent_note: string;
  status: "processing" | "ready" | "failed";
  error: string | null;
  source: "user" | "builtin";
  gender: "female" | "male" | null;
  quality_rating: Rating | null;
  quality_report: VoiceSummaryReport | null;
  speech_seconds: number;
  has_preview: boolean;
  has_transcripts: boolean;
  sort_order: number;
  generation_count: number;
  created_at: string;
  updated_at: string;
}

export interface VoiceDetail extends Voice {
  samples: Sample[];
  engines_ready: string[];
}

export interface Engine {
  name: string;
  label: string;
  languages: string[];
  available: boolean;
  reason: string;
  loaded: boolean;
  device: string | null;
  needs_transcript: boolean;
  max_ref_seconds: number | null;
  license: string;
  default: boolean;
}

export interface Chunk {
  idx: number;
  text: string;
  voice_id: string | null;
  spoken_text: string | null;
  char_start: number;
  char_end: number;
  pause_after_ms: number;
  status: string;
  duration_seconds: number | null;
  compute_seconds: number | null;
  offset_seconds: number | null;
}

export interface Generation {
  id: string;
  voice_id: string;
  voice_name: string | null;
  speakers: string[];
  engine: string;
  engine_version: string | null;
  language: string;
  script: string;
  settings: Record<string, number>;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  device: string | null;
  duration_seconds: number | null;
  compute_seconds: number | null;
  chunk_count: number;
  similarity: number | null;
  created_at: string;
}

export interface GenerationDetail extends Generation {
  chunks: Chunk[];
}

export interface JobEvent {
  type: string;
  job_id: string;
  kind: "create_voice" | "generate";
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  step: string | null;
  message: string | null;
  voice_id: string | null;
  generation_id: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  data: Record<string, unknown>;
}

export interface PronunciationEntry {
  id: string;
  term: string;
  replacement: string;
  language: string | null;
  case_sensitive: boolean;
}

export interface PronunciationPreview {
  text: string;
  applied: { term: string; replacement: string; count: number }[];
}

// ---- Endpoints ----

export const api = {
  engines: () => request<Engine[]>("/engines"),
  voices: () => request<Voice[]>("/voices"),
  voice: (id: string) => request<VoiceDetail>(`/voices/${id}`),
  updateVoice: (id: string, body: Partial<Voice>) => request<VoiceDetail>(`/voices/${id}`, json("PATCH", body)),
  deleteVoice: (id: string) =>
    request<{ files_removed: number; generations_removed: number; leftover_paths: string[] }>(
      `/voices/${id}`,
      { method: "DELETE" },
    ),
  createVoice: (form: FormData, onProgress?: (f: number) => void) =>
    upload<{ voice: Voice; job_id: string }>("/voices", form, onProgress),
  qualityCheck: (file: Blob, name: string, onProgress?: (f: number) => void, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("file", file, name);
    return upload<{ filename: string; duration: number; report: QualityReport }>(
      "/voices/quality-check",
      form,
      onProgress,
      signal,
    );
  },
  recommend: (voiceId: string, language: string) =>
    request<{ engine: string; reason: string; alternatives: { engine: string; note: string }[] }>(
      `/voices/${voiceId}/recommend?language=${language}`,
    ),
  builtinMissing: () => request<string[]>("/voices/builtin/missing"),
  restoreBuiltin: () => request<{ job_id: string } | null>("/voices/builtin/restore", { method: "POST" }),
  transcribe: (voiceId: string, force = false) =>
    request<{ job_id: string }>(`/voices/${voiceId}/transcribe${force ? "?force=true" : ""}`, { method: "POST" }),
  correctTranscript: (voiceId: string, sampleId: string, texts: string[]) =>
    request<VoiceDetail>(`/voices/${voiceId}/samples/${sampleId}/transcript`, json("PUT", { texts })),
  pronunciations: () => request<PronunciationEntry[]>("/pronunciations"),
  addPronunciation: (body: Omit<PronunciationEntry, "id">) =>
    request<PronunciationEntry>("/pronunciations", json("POST", body)),
  updatePronunciation: (id: string, body: Partial<Omit<PronunciationEntry, "id">>) =>
    request<PronunciationEntry>(`/pronunciations/${id}`, json("PATCH", body)),
  deletePronunciation: async (id: string) => {
    const res = await fetch(`/api/v1/pronunciations/${id}`, { method: "DELETE" });
    if (!res.ok) throw new ApiError(res.status, "Couldn’t delete");
  },
  previewPronunciation: (text: string, language: string) =>
    request<PronunciationPreview>("/pronunciations/preview", json("POST", { text, language })),
  generations: (voiceId?: string) =>
    request<Generation[]>(`/generations${voiceId ? `?voice_id=${voiceId}` : ""}`),
  generation: (id: string) => request<GenerationDetail>(`/generations/${id}`),
  generate: (body: {
    voice_id: string;
    script: string;
    language: string;
    engine?: string;
    settings?: Record<string, number>;
  }) => request<{ generation: GenerationDetail; job_id: string }>("/generations", json("POST", body)),
  regenerate: (id: string) =>
    request<{ generation: GenerationDetail; job_id: string }>(`/generations/${id}/regenerate`, {
      method: "POST",
    }),
  deleteGeneration: (id: string) => request<{ files_removed: number }>(`/generations/${id}`, { method: "DELETE" }),
};

export const audioUrl = {
  preview: (voiceId: string) => `/api/v1/voices/${voiceId}/preview`,
  sample: (voiceId: string, sampleId: string) => `/api/v1/voices/${voiceId}/samples/${sampleId}/audio`,
  subtitles: (id: string, format: "srt" | "vtt" = "srt") =>
    `/api/v1/generations/${id}/subtitles?format=${format}&download=true`,
  generation: (id: string, format: "wav" | "mp3" = "wav", download = false) =>
    `/api/v1/generations/${id}/audio?format=${format}${download ? "&download=true" : ""}`,
};
