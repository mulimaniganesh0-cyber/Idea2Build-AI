"""Canonical Engineering Material Registry.

Every material contains verifiable physical and mechanical properties derived from
governing engineering standards (Eurocode, ASTM, IS).
No fabricated properties are allowed.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class MaterialDefinition(BaseModel):
    material_id: str
    name: str
    category: str
    density_kg_m3: float = Field(gt=0, description="Mass density in kg/m³")
    youngs_modulus_pa: float | None = Field(default=None, description="Modulus of elasticity (E) in Pa")
    poisson_ratio: float | None = Field(default=None, ge=0.0, le=0.5, description="Poisson's ratio")
    compressive_strength_pa: float | None = Field(default=None, description="Characteristic compressive strength in Pa")
    tensile_strength_pa: float | None = Field(default=None, description="Characteristic or ultimate tensile strength in Pa")
    yield_strength_pa: float | None = Field(default=None, description="Yield strength in Pa (for ductile materials)")
    shear_modulus_pa: float | None = Field(default=None, description="Shear modulus (G) in Pa")
    thermal_expansion_per_k: float | None = Field(default=None, description="Coefficient of thermal expansion 1/K")
    source: str = Field(description="Engineering standard or published reference source")
    revision: str = Field(default="rev_mat_2024", description="Material specification revision")


_REGISTRY: dict[str, MaterialDefinition] = {
    "reinforced_concrete": MaterialDefinition(
        material_id="reinforced_concrete",
        name="Reinforced Concrete C25/30",
        category="concrete",
        density_kg_m3=2400.0,
        youngs_modulus_pa=31.0e9,  # 31 GPa
        poisson_ratio=0.20,
        compressive_strength_pa=25.0e6,  # 25 MPa characteristic cylinder strength
        tensile_strength_pa=2.6e6,  # 2.6 MPa mean axial tensile strength
        yield_strength_pa=None,
        shear_modulus_pa=12.9e9,
        thermal_expansion_per_k=10.0e-6,
        source="Eurocode 2 (EN 1992-1-1:2004 Table 3.1) / IS 456:2000",
        revision="rev_mat_2024.1",
    ),
    "masonry": MaterialDefinition(
        material_id="masonry",
        name="Clay Brick Masonry with M4 Mortar",
        category="masonry",
        density_kg_m3=1900.0,
        youngs_modulus_pa=3.5e9,  # 3.5 GPa (E ≈ 700 * fk)
        poisson_ratio=0.15,
        compressive_strength_pa=5.0e6,  # 5.0 MPa characteristic compressive strength
        tensile_strength_pa=0.35e6,  # 0.35 MPa characteristic flexural tensile strength
        yield_strength_pa=None,
        shear_modulus_pa=1.4e9,
        thermal_expansion_per_k=6.0e-6,
        source="Eurocode 6 (EN 1996-1-1:2005 Table 3.8) / IS 1905:1987",
        revision="rev_mat_2024.1",
    ),
    "structural_steel": MaterialDefinition(
        material_id="structural_steel",
        name="Structural Steel S275 / Grade 43",
        category="metal",
        density_kg_m3=7850.0,
        youngs_modulus_pa=210.0e9,  # 210 GPa
        poisson_ratio=0.30,
        compressive_strength_pa=275.0e6,
        tensile_strength_pa=430.0e6,  # Ultimate tensile strength
        yield_strength_pa=275.0e6,  # Minimum yield strength for t <= 16mm
        shear_modulus_pa=81.0e9,
        thermal_expansion_per_k=12.0e-6,
        source="Eurocode 3 (EN 1993-1-1:2005 §3.2.6) / AISC 360-16 / IS 2062:2011",
        revision="rev_mat_2024.1",
    ),
    "glass": MaterialDefinition(
        material_id="glass",
        name="Soda-Lime Architectural Float Glass",
        category="glass",
        density_kg_m3=2500.0,
        youngs_modulus_pa=70.0e9,  # 70 GPa
        poisson_ratio=0.22,
        compressive_strength_pa=1000.0e6,  # High compressive resistance
        tensile_strength_pa=45.0e6,  # Characteristic bending tensile strength (annealed)
        yield_strength_pa=None,
        shear_modulus_pa=28.7e9,
        thermal_expansion_per_k=9.0e-6,
        source="EN 572-1:2012 §5.2 / ASTM C1036-21",
        revision="rev_mat_2024.1",
    ),
    "structural_timber": MaterialDefinition(
        material_id="structural_timber",
        name="Structural Softwood Timber C24",
        category="timber",
        density_kg_m3=420.0,  # Mean density
        youngs_modulus_pa=11.0e9,  # 11 GPa mean parallel to grain
        poisson_ratio=0.30,
        compressive_strength_pa=21.0e6,  # 21 MPa parallel to grain
        tensile_strength_pa=14.5e6,  # Characteristic tensile parallel
        yield_strength_pa=None,
        shear_modulus_pa=0.69e9,
        thermal_expansion_per_k=5.0e-6,
        source="Eurocode 5 (EN 338:2016 Table 1) / EN 1995-1-1",
        revision="rev_mat_2024.1",
    ),
}

# Alias mappings for user prompts and legacy schemas
_ALIASES = {
    "concrete": "reinforced_concrete",
    "rcc": "reinforced_concrete",
    "concrete_and_masonry": "reinforced_concrete",
    "brick": "masonry",
    "brickwork": "masonry",
    "steel": "structural_steel",
    "mild_steel": "structural_steel",
    "wood": "structural_timber",
    "timber": "structural_timber",
    "glazing": "glass",
}


def get_material(material_id: str | None) -> MaterialDefinition:
    """Retrieve material definition by id or alias. Defaults to reinforced_concrete."""
    if not material_id:
        return _REGISTRY["reinforced_concrete"]
    norm = material_id.lower().strip().replace(" ", "_").replace("-", "_")
    target = _ALIASES.get(norm, norm)
    return _REGISTRY.get(target, _REGISTRY["reinforced_concrete"])


def list_materials() -> list[dict[str, Any]]:
    """Return list of all registered materials."""
    return [mat.model_dump() for mat in _REGISTRY.values()]
