/**
 * Thin fetch wrapper for the AuRIS FastAPI backend.
 * Base URL is read from NEXT_PUBLIC_API_URL (default: http://localhost:8000
 * for local dev). Errors bubble up as thrown Error instances so React
 * components can render them in an error boundary or inline.
 */
import type {
  AnalysisResponse,
  AurisConfig,
  HealthResponse,
  SummarizeRequest,
  SummarizeResponse,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // Body was not JSON; keep statusText.
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return (await res.json()) as T;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BASE_URL}/health`, { cache: "no-store" });
  return unwrap<HealthResponse>(res);
}

export async function fetchConfig(): Promise<AurisConfig> {
  const res = await fetch(`${BASE_URL}/config`, { cache: "no-store" });
  return unwrap<AurisConfig>(res);
}

export async function postAnalyze(file: File): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/analyze`, {
    method: "POST",
    body: form,
  });
  return unwrap<AnalysisResponse>(res);
}

export async function postSummarize(
  payload: SummarizeRequest,
): Promise<SummarizeResponse> {
  const res = await fetch(`${BASE_URL}/summarize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<SummarizeResponse>(res);
}
