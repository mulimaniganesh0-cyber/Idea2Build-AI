export type Unit = "mm" | "cm" | "m" | "in" | "ft";

export interface Dimensions {
  length: number;
  width: number;
  height: number;
}

export interface DesignSpec {
  schema_version: string;
  object_type:
    | "box"
    | "shaft"
    | "plate"
    | "cylinder"
    | "sphere"
    | "cone"
    | "hole"
    | "bridge"
    | "house"
    | "mechanical_bracket"
    | string;
  dimensions: Dimensions;
  unit: Unit;
  dimensions_mm: Dimensions;
  material: string | null;
  feature_parameters: Record<string, number | string>;
  source_prompt: string;
  warnings: string[];
}

export type ViewMode = "exterior" | "interior" | "cutaway" | "floor_plan" | "full_building";

export interface GeometryComponent {
  name: string;
  type: string;
  component_id?: string;
  structural?: boolean;
  classification?: string;
  material_id?: string;
  position_m: [number, number, number];
  dimensions_m: [number, number, number];
  rotation_rad?: [number, number, number];
  room_id?: string;
  floor_number?: number;
  material_color?: string;
}

export interface ParametricGeometry {
  type: string;
  unit: string;
  model_revision?: string;
  geometry_hash?: string;
  components: GeometryComponent[];
}

export type SelectionMode = "navigate" | "inspect_face" | "apply_load" | "apply_support";

export interface CADFaceMetadata {
  face_id: string;
  component_id: string;
  model_revision: string;
  geometry_hash: string;
  area_m2: number;
  area_mm2: number;
  normal: { x: number; y: number; z: number };
  center_m: { x: number; y: number; z: number };
  center_mm: { x: number; y: number; z: number };
  surface_type: string;
  structural: boolean;
  classification?: string;
  material_id?: string;
  bounding_box?: Record<string, number>;
}

export interface EngineeringLoad {
  load_id: string;
  model_id: string;
  project_id: string;
  model_revision: string;
  geometry_hash: string;
  type: "FORCE" | "PRESSURE" | "MOMENT" | "TORQUE";
  magnitude: number;
  unit: string;
  direction_x: number;
  direction_y: number;
  direction_z: number;
  component_id: string;
  face_id: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface EngineeringSupport {
  support_id: string;
  model_id: string;
  project_id: string;
  model_revision: string;
  geometry_hash: string;
  type: "FIXED" | "PINNED" | "ROLLER" | "SYMMETRY";
  component_id: string;
  face_id: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface EngineeringSummary {
  ok: boolean;
  model_id: string;
  load_count: number;
  support_count: number;
  resultant_force_N: number;
  warnings: string[];
  loads: EngineeringLoad[];
  supports: EngineeringSupport[];
}

export interface ModelAction {
  type: string;
  model_id: string;
}

export interface RequirementIssue {
  field: string;
  severity: "warning" | "error";
  message: string;
}

export interface EngineeringTask {
  id: string;
  title: string;
  specialist: string;
  depends_on: string[];
  status: "pending" | "blocked" | "ready";
  objective: string;
}

export interface ProjectPlan {
  project_id: string;
  version: number;
  source_prompt: string;
  domain: string;
  complexity: number;
  summary: string;
  tasks: EngineeringTask[];
  missing_information: RequirementIssue[];
  explicit_assumptions: string[];
  safety_notice: string;
}

export interface ProjectSession {
  plan: ProjectPlan;
  design_state: DesignSpec | null;
  design_version: number | null;
  geometry: ParametricGeometry | null;
  parametric_json: Record<string, unknown> | null;
  messages: Array<{ role: "assistant" | "user"; text: string; timestamp: string }>;
  kernel_report?: Record<string, unknown> | null;
  house_design_state?: Record<string, unknown> | null;
}
export interface ChatResponse {
  message: string;
  requires_clarification: boolean;
  questions: string[];
  suggestions: string[];
  active_domain: string | null;
  project_id: string;
  design_state: DesignSpec | null;
  model_action: ModelAction | null;
  geometry: ParametricGeometry | null;
  parametric_json?: Record<string, unknown> | null;
  knowledge_status?: string | null;
  knowledge_sources?: Array<{ document_id?: number; chunk_id?: number; rank?: number; source: string; title?: string; page?: number | null; score?: number; content?: string }> | null;
  knowledge_trace?: { trace_id: string; embedding_model: string; embedding_dimension: number | null; requested_top_k: number; similarity_threshold: number; duration_ms?: number } | null;
  cad_intent?: string | null;
  kernel_report?: Record<string, unknown> | null;
  house_design_state?: Record<string, unknown> | null;
}

export interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  text: string;
  timestamp: string;
  questions?: string[];
  suggestions?: string[];
  isError?: boolean;
}

export type SidebarRoute = "home" | "chat" | "files" | "viewer" | "dataset" | "settings";

export interface CadFileItem {
  id: string;
  name: string;
  type: "JSON" | "DWG" | "STEP" | "STL" | "IMAGE";
  size: string;
  updatedAt: string;
  downloadUrl?: string;
}

export interface DatasetMetric {
  domain: string;
  sampleCount: number;
  avgConfidence: string;
  supportedPrimitives: string[];
}

export interface UserPreferences {
  defaultUnit: Unit;
  renderShadows: boolean;
  showGridDefault: boolean;
  showAxesDefault: boolean;
  apiUrl: string;
}
