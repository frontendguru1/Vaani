import { request } from "../../lib/api";

export interface Health {
  status: "ok" | "degraded";
  app: string;
  version: string;
  database: boolean;
  ffmpeg: { available: boolean; version: string | null };
  device: {
    torch_installed: boolean;
    torch_version: string | null;
    mps_available: boolean;
    preferred: "mps" | "cpu";
  };
  transcription?: { available: boolean; model: string; downloaded: boolean; on_create: boolean };
}

export const getHealth = () => request<Health>("/health");
