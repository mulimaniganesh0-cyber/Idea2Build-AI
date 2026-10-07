import type { ChatResponse, DesignSpec, ProjectPlan, ProjectSession } from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function requestHouseDesignOptions(requirements: Record<string, unknown>, useRag = true): Promise<Record<string, any>> {
  const response = await fetch(`${API_BASE_URL}/api/house/design-options`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requirements, use_rag: useRag }) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ?? "House design planning failed.");
  return body;
}

export async function selectHouseDesignOption(projectId: string, optionId: string): Promise<Record<string, any>> {
  const response = await fetch(`${API_BASE_URL}/api/house/design-options/select`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: projectId, option_id: optionId }) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ?? "House design option selection failed.");
  return body;
}

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
// ── CAD Export API ────────────────────────────────────────────────────────
export async function exportCad(format: string, parametricJson: object): Promise<Blob> {
  const endpoint = `${API_BASE_URL}/api/cad/export/${format}`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parametric_json: parametricJson }),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : `Export ${format.toUpperCase()} failed with status ${response.status}`;
    throw new Error(detail);
  }
  const blob = await response.blob();
  return blob;
}

export async function rebuildValidate(parametricJson: object): Promise<any> {
  const endpoint = `${API_BASE_URL}/api/cad/rebuild`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parametric_json: parametricJson }),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : `Rebuild validation failed with status ${response.status}`;
    throw new Error(detail);
  }
  return response.json();
}

// Convenience wrappers
export async function exportSTEP(parametricJson: object): Promise<Blob> {
  return exportCad("step", parametricJson);
}
export async function exportSTL(parametricJson: object): Promise<Blob> {
  return exportCad("stl", parametricJson);
}
export async function exportOBJ(parametricJson: object): Promise<Blob> {
  return exportCad("obj", parametricJson);
}
export async function exportGLB(parametricJson: object): Promise<Blob> {
  return exportCad("glb", parametricJson);
}
export async function exportDXF(parametricJson: object): Promise<Blob> {
  return exportCad("dxf", parametricJson);
}
export async function exportParametricJSON(parametricJson: object): Promise<Blob> {
  return exportCad("parametric-json", parametricJson);
}


export async function listProjects(): Promise<ProjectPlan[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects`);
  if (!response.ok) throw new Error(`Project list failed with status ${response.status}`);
  return response.json() as Promise<ProjectPlan[]>;
}

export async function getProjectSession(projectId: string): Promise<ProjectSession> {
  const response = await fetch(`${API_BASE_URL}/api/v1/projects/${encodeURIComponent(projectId)}/session`);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : `Project load failed with status ${response.status}`;
    throw new Error(detail);
  }
  return response.json() as Promise<ProjectSession>;
}

// ── House CAD Engineering API ─────────────────────────────────────────────────

export interface HouseStateRequest {
  project_id: string;
  site_width_m?: number | null;
  site_length_m?: number | null;
  floors?: number;
  building_width_m?: number | null;
  building_length_m?: number | null;
  floor_height_m?: number;
  material?: string | null;
  roof_type?: string;
  version?: number;
}

async function housePost(endpoint: string, req: HouseStateRequest): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `House CAD request to ${endpoint} failed with status ${response.status}`;
    throw new Error(detail);
  }
  return response;
}

/** Generate the canonical OpenCASCADE house CAD model and return inspector data. */
export async function generateHouseCAD(req: HouseStateRequest): Promise<Record<string, unknown>> {
  const res = await housePost("/api/house/cad/generate", req);
  return res.json() as Promise<Record<string, unknown>>;
}

/** Fetch the full hierarchical component tree for the house model. */
export async function getHouseCADTree(req: HouseStateRequest): Promise<Record<string, unknown>> {
  const res = await housePost("/api/house/cad/tree", req);
  return res.json() as Promise<Record<string, unknown>>;
}

/** Fetch physical/mechanical properties (volume, mass, CoM, inertia) from the CAD kernel. */
export async function getHouseCADProperties(req: HouseStateRequest): Promise<Record<string, unknown>> {
  const res = await housePost("/api/house/cad/properties", req);
  return res.json() as Promise<Record<string, unknown>>;
}

/** Fetch per-face B-Rep metadata (area, normal, centroid, surface type). */
export async function getHouseCADFaces(req: HouseStateRequest): Promise<Record<string, unknown>> {
  const res = await housePost("/api/house/cad/faces", req);
  return res.json() as Promise<Record<string, unknown>>;
}

/** Export house as genuine STEP AP214 solid (real OpenCASCADE B-Rep). */
export async function exportHouseCADStep(req: HouseStateRequest): Promise<Blob> {
  const res = await housePost("/api/house/cad/export/step", req);
  return res.blob();
}

/** Export house as binary STL mesh tessellated from real CAD solids. */
export async function exportHouseCADStl(req: HouseStateRequest): Promise<Blob> {
  const res = await housePost("/api/house/cad/export/stl", req);
  return res.blob();
}

/** Export house as Wavefront OBJ with face normals from real CAD solids. */
export async function exportHouseCADObj(req: HouseStateRequest): Promise<Blob> {
  const res = await housePost("/api/house/cad/export/obj", req);
  return res.blob();
}

/** Download the canonical parametric JSON for the house (editable source for round-trip rebuild). */
export async function getHouseCADParametricJson(req: HouseStateRequest): Promise<Blob> {
  const res = await housePost("/api/house/cad/parametric-json", req);
  return res.blob();
}

// ── Phase 5.5: Interactive CAD Faces, Loads & Supports ────────────────────────

export async function listCADFaces(geometryHash: string): Promise<{ ok: boolean; count: number; faces: import("./types").CADFaceMetadata[] }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/cad/${encodeURIComponent(geometryHash)}/faces`);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : `Failed to fetch faces for geometry hash ${geometryHash}`;
    throw new Error(detail);
  }
  return response.json();
}

export async function inspectCADFace(params: {
  model_id: string;
  geometry_hash: string;
  model_revision: string;
  component_id: string;
  face_id: string;
}): Promise<{ ok: boolean; face: import("./types").CADFaceMetadata }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/cad/face/inspect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : "Failed to inspect CAD face";
    throw new Error(detail);
  }
  return response.json();
}

export async function createEngineeringLoad(loadReq: {
  model_id: string;
  project_id: string;
  model_revision: string;
  geometry_hash: string;
  component_id: string;
  face_id: string;
  type: string;
  magnitude: number;
  unit?: string;
  direction_x?: number;
  direction_y?: number;
  direction_z?: number;
}): Promise<{ ok: boolean; load_id: string; face: import("./types").CADFaceMetadata; warnings: string[]; message: string }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/engineering/loads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(loadReq),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : `Failed to create load: ${response.status}`;
    throw new Error(detail);
  }
  return response.json();
}

export async function listEngineeringLoads(modelId: string): Promise<{ ok: boolean; count: number; loads: import("./types").EngineeringLoad[] }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/engineering/loads/${encodeURIComponent(modelId)}`);
  if (!response.ok) throw new Error(`Failed to list loads for model ${modelId}`);
  return response.json();
}

export async function deleteEngineeringLoad(loadId: string): Promise<{ ok: boolean; load_id: string; status: string }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/engineering/loads/${encodeURIComponent(loadId)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(`Failed to delete load ${loadId}`);
  return response.json();
}

export async function createEngineeringSupport(suppReq: {
  model_id: string;
  project_id: string;
  model_revision: string;
  geometry_hash: string;
  component_id: string;
  face_id: string;
  type: string;
}): Promise<{ ok: boolean; support_id: string; face: import("./types").CADFaceMetadata; warnings: string[]; message: string }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/engineering/supports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(suppReq),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = typeof body === "object" && body !== null && "detail" in body
      ? String((body as { detail: unknown }).detail)
      : `Failed to create support: ${response.status}`;
    throw new Error(detail);
  }
  return response.json();
}

export async function listEngineeringSupports(modelId: string): Promise<{ ok: boolean; count: number; supports: import("./types").EngineeringSupport[] }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/engineering/supports/${encodeURIComponent(modelId)}`);
  if (!response.ok) throw new Error(`Failed to list supports for model ${modelId}`);
  return response.json();
}

export async function deleteEngineeringSupport(supportId: string): Promise<{ ok: boolean; support_id: string; status: string }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/engineering/supports/${encodeURIComponent(supportId)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(`Failed to delete support ${supportId}`);
  return response.json();
}

export async function getEngineeringSummary(modelId: string): Promise<import("./types").EngineeringSummary> {
  const response = await fetch(`${API_BASE_URL}/api/v1/engineering/summary/${encodeURIComponent(modelId)}`);
  if (!response.ok) throw new Error(`Failed to get engineering summary for model ${modelId}`);
  return response.json();
}
