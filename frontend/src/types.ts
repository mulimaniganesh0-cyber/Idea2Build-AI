export type Unit = "mm" | "cm" | "m" | "in" | "ft";

export interface Dimensions {
  length: number;
  width: number;
  height: number;
}

export interface DesignSpec {
  schema_version: string;
  object_type: "box" | "shaft" | "plate" | "cylinder" | "sphere" | "cone" | "hole" | "bridge" | "house" | string;
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
  components: GeometryComponent[];
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
