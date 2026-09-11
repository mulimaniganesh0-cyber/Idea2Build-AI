export type Unit = "mm" | "cm" | "m" | "in" | "ft";

export interface Dimensions {
  length: number;
  width: number;
  height: number;
}

export interface DesignSpec {
  schema_version: string;
  object_type: "box";
  dimensions: Dimensions;
  unit: Unit;
  dimensions_mm: Dimensions;
  source_prompt: string;
  warnings: string[];
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
