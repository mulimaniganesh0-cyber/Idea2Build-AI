import type { DesignSpec } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function parseDesign(prompt: string): Promise<DesignSpec> {
  const response = await fetch(`${API_BASE_URL}/api/v1/designs/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String(body.detail)
      : "The design service could not process this request.";
    throw new Error(detail);
  }
  return response.json() as Promise<DesignSpec>;
}

