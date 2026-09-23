import type { ChatResponse, DesignSpec, ProjectPlan } from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export function debugLog(label: string, data: Record<string, unknown>): void {
  if (import.meta.env.DEV) {
    console.info(`[AI-CAD DEBUG - ${new Date().toLocaleTimeString()}] ${label}`, data);
  }
}

export async function sendChatMessage(message: string, projectId: string | null): Promise<ChatResponse> {
  const endpoint = `${API_BASE_URL}/api/chat`;
  const startTime = performance.now();
  
  debugLog("Request Sent", { endpoint, payload: { message, project_id: projectId } });

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, project_id: projectId }),
    });

    const duration = Math.round(performance.now() - startTime);
    const body: unknown = await response.json().catch(() => null);

    debugLog("Response Received", {
      endpoint,
      status: response.status,
      ok: response.ok,
      durationMs: duration,
      keys: typeof body === "object" && body !== null ? Object.keys(body) : [],
    });

    if (!response.ok) {
      const detail = typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Server returned status ${response.status}`;
      throw new Error(detail);
    }

    return body as ChatResponse;
  } catch (error) {
    debugLog("Request Error", {
      endpoint,
      error: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}

export async function parseDesign(prompt: string): Promise<DesignSpec> {
  const response = await fetch(`${API_BASE_URL}/api/v1/designs/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : "The design service could not process this request.";
    throw new Error(detail);
  }
  return response.json() as Promise<DesignSpec>;
}

export async function analyzeProject(prompt: string): Promise<ProjectPlan> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : "The project-planning service could not process this request.";
    throw new Error(detail);
  }
  return response.json() as Promise<ProjectPlan>;
}
