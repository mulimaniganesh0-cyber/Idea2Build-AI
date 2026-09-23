from enum import Enum, IntEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class Unit(str, Enum):
    MILLIMETER = "mm"
    CENTIMETER = "cm"
    METER = "m"
    INCH = "in"
    FOOT = "ft"


class BridgeType(str, Enum):
    BEAM_GIRDER = "beam_girder"
    TRUSS = "truss"
    ARCH = "arch"
    SUSPENSION = "suspension"
    CABLE_STAYED = "cable_stayed"


class EngineeringDomain(str, Enum):
    MECHANICAL = "mechanical"
    CIVIL = "civil"
    STRUCTURAL = "structural"
    MULTIDISCIPLINARY = "multidisciplinary"
    UNSPECIFIED = "unspecified"


class Complexity(IntEnum):
    SINGLE_COMPONENT = 1
    MULTI_COMPONENT = 2
    ASSEMBLY = 3
    SUBSYSTEM = 4
    COMPLETE_STRUCTURE = 5
    MULTIDISCIPLINARY_PROJECT = 6
    LARGE_ENGINEERING_PROJECT = 7


class TaskStatus(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    READY = "ready"


class Dimensions(BaseModel):
    """Box dimensions expressed in the source unit supplied by the user."""

    length: float = Field(gt=0, le=10_000_000)
    width: float = Field(gt=0, le=10_000_000)
    height: float = Field(gt=0, le=10_000_000)


class DesignSpec(BaseModel):
    schema_version: str = "1.0"
    object_type: str
    dimensions: Dimensions
    unit: Unit
    dimensions_mm: Dimensions
    material: str | None = None
    feature_parameters: dict[str, float | int | str] = Field(default_factory=dict)
    source_prompt: str
    warnings: list[str] = Field(default_factory=list)


class RequirementIssue(BaseModel):
    field: str
    severity: str
    message: str


class EngineeringTask(BaseModel):
    id: str
    title: str
    specialist: str
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    objective: str


class ProjectPlan(BaseModel):
    """Persistent, inspectable project memory for a design request.

    This is deliberately structured instead of being a raw chat transcript.
    """

    project_id: str = Field(default_factory=lambda: str(uuid4()))
    version: int = 1
    source_prompt: str
    domain: EngineeringDomain
    complexity: Complexity
    summary: str
    tasks: list[EngineeringTask]
    missing_information: list[RequirementIssue] = Field(default_factory=list)
    explicit_assumptions: list[str] = Field(default_factory=list)
    safety_notice: str = (
        "Preliminary concept only. A qualified engineer must verify site conditions, "
        "loads, applicable codes, calculations, and final drawings."
    )


class ProjectRevisionRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2_000)
    project_id: str | None = None


class ModelAction(BaseModel):
    type: str
    model_id: str


class ChatResponse(BaseModel):
    message: str
    requires_clarification: bool
    questions: list[str] = Field(default_factory=list)
    project_id: str
    design_state: DesignSpec | None = None
    model_action: ModelAction | None = None
    suggestions: list[str] = Field(default_factory=list)
    active_domain: str | None = None
    geometry: "ParametricGeometry | None" = None


class BridgeProjectState(BaseModel):
    project_id: str
    project_type: str = "pedestrian_bridge"
    domain: str = "civil_engineering"
    span_m: float | None = None
    deck_width_m: float | None = None
    support_height_m: float | None = 5.0
    arch_height_m: float | None = None
    tower_height_m: float | None = None
    truss_height_m: float | None = None
    cable_sag_m: float | None = None
    number_of_panels: int | None = None
    crossing_environment: str | None = None
    bridge_concept: str | None = None
    bridge_type: BridgeType | None = None
    material: str | None = None
    status: str = "requirements_pending"
    assumptions: list[str] = Field(default_factory=list)


class HouseProjectState(BaseModel):
    project_id: str
    project_type: str = "residential_house"
    domain: str = "architectural_civil"
    site_width_m: float | None = None
    site_length_m: float | None = None
    floors: int = Field(default=2, ge=1, le=50)
    ground_floor_included: bool = True
    upper_floor_count: int = 1
    floor_label: str = "G+1"
    building_width_m: float | None = None
    building_length_m: float | None = None
    floor_height_m: float = 3.0
    total_height_m: float = 7.2
    material: str | None = "concrete_and_masonry"
    roof_type: str = "pitched"
    view_mode: str = "exterior"
    active_floor: int | None = None
    custom_furniture: list[dict] = Field(default_factory=list)
    unit: str = "ft"
    status: str = "requirements_pending"
    assumptions: list[str] = Field(default_factory=list)


class CadGenerationResponse(BaseModel):
    success: bool = True
    model_id: str
    format: str = "parametric-viewer-geometry"
    model_url: str | None = None
    parameters: DesignSpec
    validation: list[str] = Field(default_factory=lambda: ["Schema and unit validation passed."])
    geometry: "ParametricGeometry"


class GeometryComponent(BaseModel):
    name: str
    type: str
    position_m: tuple[float, float, float] = (0, 0, 0)
    dimensions_m: tuple[float, float, float]
    rotation_rad: tuple[float, float, float] = (0.0, 0.0, 0.0)
    room_id: str | None = None
    floor_number: int | None = None
    material_color: str | None = None


class ParametricGeometry(BaseModel):
    type: str
    unit: str = "m"
    components: list[GeometryComponent]


class ParseRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1_000)

    @field_validator("prompt")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt cannot be blank")
        return value.strip()


class HealthResponse(BaseModel):
    status: str
    service: str
