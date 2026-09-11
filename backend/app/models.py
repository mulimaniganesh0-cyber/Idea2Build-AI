from enum import Enum, IntEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class Unit(str, Enum):
    MILLIMETER = "mm"
    CENTIMETER = "cm"
    METER = "m"
    INCH = "in"
    FOOT = "ft"


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

    length: float = Field(gt=0, le=100_000)
    width: float = Field(gt=0, le=100_000)
    height: float = Field(gt=0, le=100_000)


class DesignSpec(BaseModel):
    schema_version: str = "1.0"
    object_type: str = "box"
    dimensions: Dimensions
    unit: Unit
    dimensions_mm: Dimensions
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
