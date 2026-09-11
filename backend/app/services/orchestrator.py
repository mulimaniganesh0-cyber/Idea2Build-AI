"""Deterministic project planner used before an LLM/RAG layer is introduced.

The service makes its limitations visible: it produces an auditable task graph and
flags missing critical inputs instead of inventing engineering facts.
"""

from app.models import (
    Complexity,
    EngineeringDomain,
    EngineeringTask,
    ProjectPlan,
    RequirementIssue,
    TaskStatus,
)


_CIVIL_TERMS = {"building", "bridge", "warehouse", "house", "hospital", "road", "foundation", "beam", "column", "site", "drainage"}
_MECHANICAL_TERMS = {"bracket", "shaft", "gear", "bearing", "gearbox", "machine", "bolt", "plate", "cylinder", "housing", "assembly"}
_LARGE_TERMS = {"hospital", "factory", "commercial", "multi-storey", "multistory", "five-storey", "five story"}


def _domain(prompt: str) -> EngineeringDomain:
    words = set(prompt.lower().replace("-", " ").split())
    civil = bool(words & _CIVIL_TERMS)
    mechanical = bool(words & _MECHANICAL_TERMS)
    if civil and mechanical:
        return EngineeringDomain.MULTIDISCIPLINARY
    if civil:
        return EngineeringDomain.CIVIL
    if mechanical:
        return EngineeringDomain.MECHANICAL
    return EngineeringDomain.UNSPECIFIED


def _complexity(prompt: str, domain: EngineeringDomain) -> Complexity:
    lower = prompt.lower()
    if any(term in lower for term in _LARGE_TERMS):
        return Complexity.LARGE_ENGINEERING_PROJECT
    if domain is EngineeringDomain.MULTIDISCIPLINARY:
        return Complexity.MULTIDISCIPLINARY_PROJECT
    if any(term in lower for term in ("building", "bridge", "warehouse", "assembly")):
        return Complexity.COMPLETE_STRUCTURE
    if any(term in lower for term in ("bracket", "shaft", "room", "wall", "beam", "plate")):
        return Complexity.SINGLE_COMPONENT
    return Complexity.MULTI_COMPONENT


def _task(task_id: str, title: str, specialist: str, objective: str, *depends_on: str) -> EngineeringTask:
    return EngineeringTask(
        id=task_id,
        title=title,
        specialist=specialist,
        objective=objective,
        depends_on=list(depends_on),
        status=TaskStatus.READY if not depends_on else TaskStatus.PENDING,
    )


def create_plan(prompt: str, project_id: str | None = None, version: int = 1) -> ProjectPlan:
    domain = _domain(prompt)
    complexity = _complexity(prompt, domain)
    lower = prompt.lower()
    missing: list[RequirementIssue] = []

    if domain is EngineeringDomain.UNSPECIFIED:
        missing.append(RequirementIssue(field="engineering_domain", severity="error", message="State whether this is civil, mechanical, structural, or multidisciplinary work."))
    if complexity >= Complexity.COMPLETE_STRUCTURE and not any(unit in lower for unit in ("mm", " cm", " m", "ft", "metre", "meter")):
        missing.append(RequirementIssue(field="dimensions", severity="warning", message="Provide the principal dimensions/site limits and preferred unit system."))
    if any(term in lower for term in ("building", "bridge", "warehouse", "foundation")):
        missing.append(RequirementIssue(field="loads_and_codes", severity="error", message="Provide location, design loads, site/soil data where relevant, and governing code/standard. Do not assume these for a real design."))
    if "bridge" in lower:
        missing.append(RequirementIssue(field="crossing_conditions", severity="warning", message="Provide span arrangement, clearance/hydrology, access, and environmental constraints."))

    tasks = [
        _task("requirements", "Requirements and assumptions", "Requirement agent", "Extract requirements, ask for critical gaps, and maintain the design brief."),
        _task("concepts", "Concept alternatives", "Design ideation agent", "Create and compare appropriate preliminary concepts.", "requirements"),
        _task("parameters", "Parametric specification", "Domain design agent", "Create an editable engineering specification with explicit units.", "concepts"),
        _task("calculations", "Deterministic calculations", "Calculation engine", "Run applicable formulae with traceable inputs and assumptions.", "parameters"),
        _task("cad", "Parametric CAD generation", "CAD agent", "Generate component geometry from the validated specification.", "parameters"),
        _task("validation", "Validation and professional review", "Validation agent", "Validate schema, units, geometry, constraints, and review requirements.", "calculations", "cad"),
        _task("report", "Preliminary design report", "Documentation agent", "Document assumptions, results, warnings, sources, and review requirements.", "validation"),
    ]
    if domain in (EngineeringDomain.CIVIL, EngineeringDomain.MULTIDISCIPLINARY):
        tasks.insert(2, _task("site", "Site and regulatory inputs", "Civil/structural agent", "Capture site, access, hazards, and applicable regulation inputs.", "requirements"))
    if domain is EngineeringDomain.MULTIDISCIPLINARY:
        tasks.insert(3, _task("systems", "Systems coordination", "Systems agent", "Coordinate structural, mechanical, electrical, plumbing, and safety interfaces.", "site"))

    assumptions = ["No professional certification, construction approval, or manufacturing release is implied."]
    if missing:
        assumptions.append("Critical missing information is intentionally left unresolved and must be supplied or formally approved as an assumption.")
    plan = ProjectPlan(
        source_prompt=prompt,
        domain=domain,
        complexity=complexity,
        summary=f"{domain.value.title()} request classified at complexity level {int(complexity)}.",
        tasks=tasks,
        missing_information=missing,
        explicit_assumptions=assumptions,
        version=version,
    )
    if project_id:
        plan.project_id = project_id
    return plan

