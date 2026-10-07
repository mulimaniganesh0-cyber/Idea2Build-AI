"""Pydantic models for mechanical engineering designs.

These are separate from the generic DesignSpec so that the mechanical
pipeline can be validated and rejected before any CAD is generated.
"""

from pydantic import BaseModel, Field, model_validator


class HoleDef(BaseModel):
    diameter_mm: float = Field(gt=0)
    count: int = Field(ge=1)
    location: str = "base"  # 'base' | 'upright' | 'custom'
    description: str = ""


class FilletDef(BaseModel):
    radius_mm: float = Field(ge=0)
    location: str = "external_vertical"


class ChamferDef(BaseModel):
    size_mm: float = Field(ge=0)
    angle_deg: float = 45.0
    location: str = "hole_entries"


class BasePlateDef(BaseModel):
    length_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)


class UprightPlateDef(BaseModel):
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)


class GussetDef(BaseModel):
    count: int = Field(ge=0, default=0)
    type: str = "triangular"  # 'triangular' | 'rectangular'


class MechanicalDesignSpec(BaseModel):
    """Validated structured spec for a mechanical part.

    The LLM fills this. The CAD kernel consumes it.
    The validator ensures no architectural fields are present.
    """

    domain: str = "mechanical"
    object_type: str
    units: str = "mm"

    base_plate: BasePlateDef | None = None
    upright_plate: UprightPlateDef | None = None
    gussets: GussetDef = Field(default_factory=GussetDef)
    holes: list[HoleDef] = Field(default_factory=list)
    fillets: list[FilletDef] = Field(default_factory=list)
    chamfers: list[ChamferDef] = Field(default_factory=list)
    material: str = "steel"
    parametric: bool = True
    source_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)

    # Dimensions fallback (for simple mechanical shapes that are not brackets)
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    diameter_mm: float | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_architectural_fields(cls, data: dict) -> dict:
        """Ensure no architectural hallucinations slip into a mechanical spec."""
        if isinstance(data, dict):
            _BAD_KEYS = {
                "floor_count", "floor_height", "roof_type", "rooms", "bedrooms",
                "g+1", "g+2", "site_width", "building_length", "floors", "site_length",
            }
            found = set(k.lower() for k in data.keys()) & _BAD_KEYS
            if found:
                raise ValueError(
                    f"Architectural fields are forbidden inside a mechanical DesignSpec: {found}. "
                    "Reject and re-classify."
                )
        return data

    @model_validator(mode="after")
    def validate_positive_dims(self) -> "MechanicalDesignSpec":
        if self.base_plate:
            for dim in (self.base_plate.length_mm, self.base_plate.width_mm, self.base_plate.thickness_mm):
                if dim <= 0:
                    raise ValueError("Base plate dimensions must be positive.")
        if self.upright_plate:
            for dim in (self.upright_plate.width_mm, self.upright_plate.height_mm, self.upright_plate.thickness_mm):
                if dim <= 0:
                    raise ValueError("Upright plate dimensions must be positive.")
        self.holes = [h for h in self.holes if h.diameter_mm > 0 and h.count > 0]
        self.fillets = [f for f in self.fillets if f.radius_mm > 0]
        self.chamfers = [c for c in self.chamfers if c.size_mm > 0]
        return self

    def feature_history(self) -> list[str]:
        """Return a flat ordered list of CAD feature operations."""
        history: list[str] = []
        if self.base_plate:
            history.append("Base plate extrusion")
        if self.upright_plate:
            history.append("Upright plate extrusion")
        if self.gussets and self.gussets.count > 0:
            for i in range(self.gussets.count):
                history.append(f"{'Left' if i == 0 else 'Right'} triangular gusset")
        for hole in self.holes:
            history.append(f"{hole.location.replace('_', ' ').title()} Ø{hole.diameter_mm:g} holes ({hole.count}×)")
        for fillet in self.fillets:
            history.append(f"R{fillet.radius_mm:g} fillets ({fillet.location})")
        for chamfer in self.chamfers:
            history.append(f"{chamfer.size_mm:g} mm × {chamfer.angle_deg:g}° chamfers ({chamfer.location})")
        return history
