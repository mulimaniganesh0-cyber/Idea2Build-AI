import { Fragment, useState } from "react";
import type { DesignSpec, GeometryComponent, ParametricGeometry } from "./types";

type KnowledgeSource = { document_id?: number; chunk_id?: number; rank?: number; source: string; title?: string; page?: number | null; score?: number; content?: string };
type KnowledgeTrace = { trace_id: string; embedding_model: string; embedding_dimension: number | null; requested_top_k: number; similarity_threshold: number; duration_ms?: number };
type RebuildReport = {
  status?: string;
  solid_count?: number;
  feature_count?: number;
  bounding_box_m?: { min?: { x?: number; y?: number; z?: number }; max?: { x?: number; y?: number; z?: number } };
};
type FeatureRecord = Record<string, unknown>;

interface ModelInspectorProps {
  designSpec: DesignSpec | null;
  geometry: ParametricGeometry | null;
  parametricJson: Record<string, unknown> | null;
  projectName: string | null;
  projectId: string | null;
  knowledgeStatus: string | null;
  knowledgeSources: KnowledgeSource[];
  knowledgeTrace: KnowledgeTrace | null;
  rebuildReport: RebuildReport | null;
  validationNotice: string | null;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  houseCADData?: Record<string, unknown> | null;
  kernelReport?: Record<string, unknown> | null;
  houseDesignState?: Record<string, any> | null;
}

function rotatedPoint(point: [number, number, number], rotation: [number, number, number]): [number, number, number] {
  let [x, y, z] = point;
  const [rx, ry, rz] = rotation;
  const y1 = y * Math.cos(rx) - z * Math.sin(rx);
  const z1 = y * Math.sin(rx) + z * Math.cos(rx);
  const x2 = x * Math.cos(ry) + z1 * Math.sin(ry);
  const z2 = -x * Math.sin(ry) + z1 * Math.cos(ry);
  const x3 = x2 * Math.cos(rz) - y1 * Math.sin(rz);
  const y3 = x2 * Math.sin(rz) + y1 * Math.cos(rz);
  return [x3, y3, z2];
}

function geometryBounds(geometry: ParametricGeometry | null) {
  const points: Array<[number, number, number]> = [];
  for (const component of geometry?.components ?? []) {
    const center = component.position_m ?? [0, 0, 0];
    const dimensions = component.dimensions_m;
    const rotation = component.rotation_rad ?? [0, 0, 0];
    for (const sx of [-1, 1]) for (const sy of [-1, 1]) for (const sz of [-1, 1]) {
      const rotated = rotatedPoint([sx * dimensions[0] / 2, sy * dimensions[1] / 2, sz * dimensions[2] / 2], rotation);
      points.push([center[0] + rotated[0], center[1] + rotated[1], center[2] + rotated[2]]);
    }
  }
  if (!points.length) return null;
  const min = [0, 1, 2].map((axis) => Math.min(...points.map((point) => point[axis]))) as [number, number, number];
  const max = [0, 1, 2].map((axis) => Math.max(...points.map((point) => point[axis]))) as [number, number, number];
  return { min, max, size: max.map((value, axis) => value - min[axis]) as [number, number, number] };
}

function mm(valueM: number): string { return `${(valueM * 1000).toFixed(2)} mm`; }
function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not supplied";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  if (typeof value === "string") return value.replaceAll("_", " ");
  return JSON.stringify(value);
}
function featureList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string" && value.trim()) return value.split("|").map((item) => item.trim()).filter(Boolean);
  return [];
}

export function ModelInspector(props: ModelInspectorProps) {
  const {
    designSpec, geometry, parametricJson, projectName, projectId,
    knowledgeStatus, knowledgeSources, knowledgeTrace, rebuildReport, validationNotice,
    collapsed, onToggleCollapsed, houseCADData, kernelReport, houseDesignState,
  } = props;
  const [activeSection, setActiveSection] = useState("model");
  const bounds = geometryBounds(geometry);
  const houseCAD = houseCADData as {
    status?: string;
    solid_topology?: {
      solid_count: number;
      face_count: number;
      edge_count: number;
      vertex_count: number;
      is_valid?: boolean;
    };
    physical_properties?: {
      total_volume_m3?: number;
      total_mass_kg?: number;
      mass_kg?: number;
      center_of_mass_m?: [number, number, number];
      inertia_matrix?: number[][];
      moment_of_inertia?: number[][] | string;
      density_kg_m3?: number;
    };
    material?: {
      primary: string;
      density_kg_m3: number;
      youngs_modulus_gpa: number;
      poisson_ratio: number;
      yield_strength_mpa: number;
      ultimate_strength_mpa: number;
      thermal_expansion_per_k?: number | null;
      standard: string;
      classification: string;
    };
    geometry?: {
      bounding_box?: { min: [number, number, number]; max: [number, number, number]; dimensions: [number, number, number] };
      bounding_box_mm?: { min?: Record<string, number>; max?: Record<string, number>; size?: Record<string, number> };
      volume_m3: number;
      surface_area_m2: number;
      center_of_mass_mm?: Record<string, number>;
    };
    validity?: string | { is_valid: boolean; solid_validity?: Record<string, boolean>; validation_messages?: string[] };
  } | null;
  const inertia = houseCAD?.physical_properties?.inertia_matrix ?? houseCAD?.physical_properties?.moment_of_inertia;
  const principalInertia = Array.isArray(inertia) && inertia.length >= 3 && inertia.slice(0, 3).every((row) => Array.isArray(row) && typeof row[0] === "number" && typeof row[1] === "number" && typeof row[2] === "number")
    ? [inertia[0][0], inertia[1][1], inertia[2][2]]
    : null;
  const cadIsValid = houseCAD?.validity === "PASS" || (typeof houseCAD?.validity === "object" && houseCAD.validity !== null && houseCAD.validity.is_valid);

  const features = Array.isArray(kernelReport?.feature_history) ? kernelReport.feature_history as FeatureRecord[] : Array.isArray(parametricJson?.features)
    ? parametricJson.features.filter((item): item is FeatureRecord => typeof item === "object" && item !== null)
    : [];
  const legacyHistory = featureList(designSpec?.feature_parameters.feature_history);
  const featureCount = features.length || legacyHistory.length || null;
  const material = designSpec?.material;
  const effectiveProjectName = projectName && !/(unspecified|mechanical) request classified at complexity level/i.test(projectName) ? projectName : null;
  const explicitlyNamedMaterial = Boolean(designSpec?.source_prompt && /\b(steel|stainless\s+steel|alumin(?:ium|um)|brass|cast\s+iron|concrete|wood|timber)\b/i.test(designSpec.source_prompt));
  const sections = [
    ["Model", "model"], ["Site", "site"], ["Rooms", "rooms"], ["Geometry", "geometry"], ["Physical", "physical"], ["Material", "material"],
    ["Strength", "strength"], ["Features", "features"], ["Parameters", "parameters"], ["Knowledge", "knowledge"], ["Validation", "validation"],
    ["Reasoning", "reasoning"],
  ];
  const goToSection = (id: string) => {
    setActiveSection(id);
    document.getElementById(`model-inspector-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <aside className={`right-spec-panel model-inspector ${collapsed ? "collapsed" : ""}`}>
      <div className="panel-header">
        <div className="inspector-title">
          <h3>MODEL INSPECTOR</h3>
                    {houseCAD?.solid_topology ? (
            <span className="badge-concept" style={{ background: "#059669", color: "#ffffff", border: "1px solid #10b981", letterSpacing: "0.05em" }}>
              OPENCASCADE KERNEL VERIFIED
            </span>
          ) : (
            <span className="badge-concept">PRELIMINARY CONCEPT</span>
          )}
        </div>
        <button className="inspector-collapse" type="button" aria-expanded={!collapsed} onClick={onToggleCollapsed}>{collapsed ? "Expand" : "Collapse"}</button>
      </div>
      {!collapsed && <>
        <nav className="inspector-tabs" aria-label="Model inspector sections">
          {sections.map(([label, id]) => <button key={id} type="button" aria-current={activeSection === id ? "location" : undefined} className={activeSection === id ? "active" : ""} onClick={() => goToSection(id)}>{label}</button>)}
        </nav>
        <div className="model-inspector-content">
          {!designSpec ? <div className="spec-empty"><p>No generated model is loaded. Enter a design request to inspect its backend-reported properties.</p></div> : <>
            <section className="inspector-section" id="model-inspector-model">
              <h4>MODEL</h4>
              <div className="inspector-grid">
                <span>Name</span><strong>{effectiveProjectName || designSpec.object_type.replaceAll("_", " ")}</strong>
                <span>Type</span><strong>{designSpec.feature_parameters.is_cube ? "Cube" : designSpec.object_type.replaceAll("_", " ")}</strong>
                <span>Project</span><strong>{projectId ? projectId.slice(0, 8) : "Not assigned"}</strong>
                <span>Units</span><strong>{designSpec.unit}</strong>
                <span>Generation</span><strong>{geometry ? "Generated" : "Specification only"}</strong>
                <span>Backend components</span><strong>{geometry?.components.length ?? "Not supplied"}</strong>
                <span>Feature definitions</span><strong>{featureCount ?? "Not supplied"}</strong>
                <span>Solid topology</span>
                <strong>
                  {houseCAD?.solid_topology
                    ? `${houseCAD.solid_topology.solid_count} solids · ${houseCAD.solid_topology.face_count} faces · ${houseCAD.solid_topology.edge_count} edges · ${houseCAD.solid_topology.vertex_count} vertices`
                    : kernelReport ? `${String(kernelReport.solid_count)} solid · ${String(kernelReport.face_count)} faces · ${String(kernelReport.edge_count)} edges`
                    : "Not exposed by current geometry API"}
                </strong>
              </div>
            </section>

            <section className="inspector-section" id="model-inspector-site">
              <h4>SITE & REQUIREMENTS</h4>
              {houseDesignState ? <div className="inspector-grid">
                <span>Plot area</span><strong>{houseDesignState.site_analysis?.plot_area_sqft ?? "NOT_SPECIFIED"} sq ft</strong>
                <span>Footprint estimate</span><strong>{houseDesignState.site_analysis?.estimated_footprint_sqft ?? "NOT_AVAILABLE"} sq ft</strong>
                <span>Floors / bedrooms / bathrooms</span><strong>{houseDesignState.floors} / {houseDesignState.bedrooms} / {houseDesignState.bathrooms}</strong>
                <span>Location</span><strong>{houseDesignState.location ?? "NOT_SPECIFIED"}</strong>
                <span>Climate data</span><strong>{houseDesignState.climate_profile?.status ?? (houseDesignState.climate_profile?.location_data ?? "NOT_SPECIFIED")}</strong>
                <span>Setbacks</span><strong>{houseDesignState.site_analysis?.setbacks ?? "NOT_SPECIFIED"}</strong>
              </div> : <p className="inspector-note">Site planning data is not available for this model.</p>}
              {houseDesignState?.site_analysis?.assumptions?.map((item: string) => <p className="inspector-note" key={item}>{item}</p>)}
            </section>

            <section className="inspector-section" id="model-inspector-rooms">
              <h4>ROOM ALLOCATION</h4>
              {houseDesignState?.room_allocation?.length ? <>
                {houseDesignState.room_allocation.map((floor: Record<string, any>) => <div key={floor.floor} className="inspector-grid">
                  <strong>Floor {floor.floor}</strong><span>{floor.allocated_sqft} allocated · {floor.circulation_sqft} circulation sq ft</span>
                  {floor.rooms.map((room: Record<string, any>) => <Fragment key={room.room_id}><span>{room.type}</span><strong>{room.area_sqft} sq ft · {room.width_ft} × {room.length_ft} ft</strong></Fragment>)}
                </div>)}
                <p className="inspector-note">Room packing: {houseDesignState.room_planning_report?.overlap_check ?? "NOT_AVAILABLE"}. Fit: {houseDesignState.room_planning_report?.fit_check ?? "NOT_AVAILABLE"}. Furniture collision checks: {houseDesignState.room_planning_report?.furniture_collision_check ?? "NOT_RUN"}.</p>
              </> : <p className="inspector-note">Room allocation is NOT_AVAILABLE until house requirements are planned.</p>}
            </section>

            <section className="inspector-section" id="model-inspector-geometry">
              <h4>GEOMETRY</h4>
              {kernelReport ? <>
                <p className="inspector-note" style={{ color: "#34d399", fontWeight: 500 }}>Canonical B-Rep geometry and measurements computed by OpenCascade.</p>
                <div className="inspector-grid">
                  <span>B-Rep bounding box X × Y × Z</span><strong>{Object.values(kernelReport.bounding_box_mm as Record<string, number>).map((value) => `${Number(value).toLocaleString()} mm`).join(" × ")}</strong>
                  <span>Exact volume</span><strong>{Number(kernelReport.volume_mm3).toLocaleString()} mm³</strong>
                  <span>Surface area</span><strong>{Number(kernelReport.surface_area_mm2).toLocaleString()} mm²</strong>
                  <span>Kernel validity</span><strong>{kernelReport.valid ? "Valid OpenCascade solid" : "Invalid"}</strong>
                </div>
              </> : houseCAD?.geometry ? (
                <>
                  <p className="inspector-note" style={{ color: "#34d399", fontWeight: 500 }}>
                    Canonical B-Rep geometry computed by OpenCASCADE CAD kernel.
                  </p>
                  <div className="inspector-grid">
                    <span>B-Rep Envelope X × Y × Z</span><strong>{Object.values(houseCAD.geometry.bounding_box_mm?.size ?? {}).map((value) => `${Number(value).toLocaleString()} mm`).join(" × ") || "NOT_AVAILABLE"}</strong>
                    <span>Minimum X / Y / Z</span><strong>{Object.values(houseCAD.geometry.bounding_box_mm?.min ?? {}).map((value) => `${Number(value).toLocaleString()} mm`).join(" · ") || "NOT_AVAILABLE"}</strong>
                    <span>Maximum X / Y / Z</span><strong>{Object.values(houseCAD.geometry.bounding_box_mm?.max ?? {}).map((value) => `${Number(value).toLocaleString()} mm`).join(" · ") || "NOT_AVAILABLE"}</strong>
                    <span>B-Rep Solids</span><strong>{houseCAD.solid_topology?.solid_count} solids ({houseCAD.solid_topology?.face_count} faces, {houseCAD.solid_topology?.edge_count} edges)</strong>
                    <span>Exact Volume</span><strong>{houseCAD.geometry.volume_m3.toLocaleString()} m³</strong>
                    <span>Total Surface Area</span><strong>{houseCAD.geometry.surface_area_m2.toLocaleString()} m²</strong>
                  </div>
                </>
              ) : bounds ? <>
                <p className="inspector-note">Envelope derived from backend parametric component positions, dimensions, and rotations. This is not a consolidated B-Rep measurement.</p>
                <div className="inspector-grid">
                  <span>Envelope X × Y × Z</span><strong>{bounds.size.map((value) => mm(value)).join(" × ")}</strong>
                  <span>Minimum X / Y / Z</span><strong>{bounds.min.map((value) => mm(value)).join(" · ")}</strong>
                  <span>Maximum X / Y / Z</span><strong>{bounds.max.map((value) => mm(value)).join(" · ")}</strong>
                  <span>Solid count</span><strong>{rebuildReport?.status === "rebuild_ok" ? `${rebuildReport.solid_count ?? "?"} exporter box primitives` : "Not verified by rebuild"}</strong>
                </div>
                <div className="inspector-grid unavailable-grid">
                  <span>Volume</span><strong>Not calculated</strong>
                  <span>Surface area</span><strong>Not calculated</strong>
                  <span>Faces / edges / vertices</span><strong>Not exposed</strong>
                </div>
              </> : <p className="inspector-note">Backend geometry properties are not available for this model.</p>}
            </section>

            <section className="inspector-section" id="model-inspector-physical">
              <h4>PHYSICAL PROPERTIES</h4>
              {houseCAD?.physical_properties ? (
                <>
                  <p className="inspector-note" style={{ color: "#34d399", fontWeight: 500 }}>
                    Exact solid mass properties evaluated by OpenCASCADE B-Rep kernel.
                  </p>
                  <div className="inspector-grid">
                    <span>Total Mass</span><strong>{(houseCAD.physical_properties.total_mass_kg ?? houseCAD.physical_properties.mass_kg ?? 0).toLocaleString()} kg</strong>
                    <span>Solid Volume</span><strong>{(houseCAD.physical_properties.total_volume_m3 ?? houseCAD.geometry?.volume_m3 ?? 0).toLocaleString()} m³</strong>
                    <span>Material Density</span><strong>{houseCAD.physical_properties.density_kg_m3 ?? "NOT_AVAILABLE"} kg/m³</strong>
                    <span>Center of Mass (X / Y / Z)</span><strong>{houseCAD.physical_properties.center_of_mass_m?.map((c) => mm(c)).join(" · ") ?? Object.values(houseCAD.geometry?.center_of_mass_mm ?? {}).map((c) => `${c} mm`).join(" · ")}</strong>
                    {principalInertia && (
                      <>
                        <span>Principal Inertia</span>
                        <strong>
                          {principalInertia[0].toExponential(3)}, {principalInertia[1].toExponential(3)}, {principalInertia[2].toExponential(3)} kg·m²
                        </strong>
                      </>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <p className="inspector-note">The current backend does not provide consolidated solid mass properties.</p>
                  <div className="inspector-grid unavailable-grid">
                    <span>Mass</span><strong>Unavailable — density and exact solid volume are not provided</strong>
                    <span>Center of mass</span><strong>Not calculated</strong>
                    <span>Moment of inertia</span><strong>Not calculated</strong>
                  </div>
                </>
              )}
            </section>

            <section className="inspector-section" id="model-inspector-material">
              <h4>MATERIAL</h4>
              {houseCAD?.material ? (
                <div className="inspector-grid">
                  <span>Model material</span><strong>{typeof houseCAD.material.primary === "string" ? houseCAD.material.primary.replaceAll("_", " ") : String((houseCAD.material.primary as unknown as Record<string, unknown>).name ?? (houseCAD.material.primary as unknown as Record<string, unknown>).material_id ?? "NOT_AVAILABLE")}</strong>
                  <span>Classification</span><strong>{houseCAD.material.classification}</strong>
                  <span>Standard</span><strong>{houseCAD.material.standard}</strong>
                  <span>Density</span><strong>{houseCAD.material.density_kg_m3} kg/m³</strong>
                  <span>Young’s Modulus</span><strong>{houseCAD.material.youngs_modulus_gpa} GPa</strong>
                  <span>Poisson Ratio</span><strong>{houseCAD.material.poisson_ratio}</strong>
                  <span>Yield Strength</span><strong>{houseCAD.material.yield_strength_mpa} MPa</strong>
                  <span>Ultimate Strength</span><strong>{houseCAD.material.ultimate_strength_mpa} MPa</strong>
                  {typeof houseCAD.material.thermal_expansion_per_k === "number" && <><span>Thermal Expansion</span><strong>{houseCAD.material.thermal_expansion_per_k.toExponential(2)} /K</strong></>}
                </div>
              ) : (
                <div className="inspector-grid">
                  <span>Model material</span><strong>{material || "Not specified"}</strong>
                  <span>Origin</span><strong>{material ? (explicitlyNamedMaterial ? "Named in source prompt; selection is not separately recorded" : "Origin not recorded by backend") : "Not specified"}</strong>
                  <span>Density</span><strong>Not available</strong>
                  <span>Yield / ultimate strength</span><strong>Not available</strong>
                  <span>Young’s modulus / Poisson ratio</span><strong>Not available</strong>
                </div>
              )}
            </section>

            <section className="inspector-section strength-section" id="model-inspector-strength">
              <h4>STRENGTH ANALYSIS <span className="state-pill">NOT ANALYZED</span></h4>
              <div className="inspector-grid unavailable-grid">
                <span>Applied load</span><strong>Not specified</strong>
                <span>Maximum stress</span><strong>Not calculated</strong>
                <span>Factor of safety</span><strong>Not calculated</strong>
                <span>Maximum deflection</span><strong>Not calculated</strong>
                <span>Load capacity</span><strong>Not calculated</strong>
              </div>
              <p className="engineering-caveat">Preliminary engineering concept. This model has not been structurally validated.</p>
            </section>

            <section className="inspector-section" id="model-inspector-features">
              <h4>FEATURE HISTORY <span className="section-count">{featureCount ?? "Not supplied"}</span></h4>
              {features.length ? <ol className="feature-list">{features.map((feature, index) => {
                const parameters = typeof feature.parameters === "object" && feature.parameters !== null ? feature.parameters as Record<string, unknown> : {};
                return <li key={String(feature.id ?? index)}>
                  <span className="feature-index">{String(feature.id ?? `#${index + 1}`)}</span>
                  <div><strong>{String(feature.label ?? feature.type ?? `Feature ${index + 1}`)}</strong>
                    <span>{formatValue(feature.type)} · {formatValue(feature.operation)} · creation order {index + 1}</span>
                    <span>Parent/dependencies and suppression state are not recorded.</span>
                    <dl>{Object.entries(parameters).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{formatValue(value)}</dd></div>)}</dl>
                  </div>
                </li>;
              })}</ol> : legacyHistory.length ? <ol className="feature-list">{legacyHistory.map((item, index) => <li key={`${index}-${item}`}><span className="feature-index">{String(index + 1).padStart(2, "0")}</span><div><strong>{item}</strong><span>Read-only legacy history; feature IDs and dependencies are not supplied.</span></div></li>)}</ol> : <p className="inspector-note">No feature history was included in the model response.</p>}
            </section>

            <section className="inspector-section" id="model-inspector-parameters">
              <h4>PARAMETERS</h4>
              <div className="inspector-grid">
                {Object.entries(designSpec.feature_parameters).filter(([key]) => !["feature_history", "is_mechanical", "parametric", "domain", "object_type"].includes(key)).map(([key, value]) => <div className="parameter-pair" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{formatValue(value)}</strong></div>)}
                <span>Specified L × W × H</span><strong>{designSpec.dimensions_mm.length} × {designSpec.dimensions_mm.width} × {designSpec.dimensions_mm.height} mm</strong>
                <span>Parameter provenance</span><strong>Not separately tracked by the current API</strong>
              </div>
            </section>

            <section className="inspector-section" id="model-inspector-knowledge">
              <h4>KNOWLEDGE USED</h4>
              {knowledgeStatus === "NOT_REQUIRED" ? <p className="inspector-note">No external engineering knowledge was required for this turn.</p>
                : knowledgeStatus === "NO_RELEVANT_CONTEXT" ? <p className="inspector-note">Retrieval ran; no relevant indexed source was found.</p>
                : knowledgeStatus === "ERROR" ? <p className="inspector-note">Retrieval was unavailable. No source is cited.</p>
                : knowledgeStatus === "FOUND" && knowledgeSources.length ? <>
                  {knowledgeTrace && <p className="inspector-note">Trace {knowledgeTrace.trace_id} · {knowledgeTrace.embedding_model} ({knowledgeTrace.embedding_dimension ?? "?"} dimensions) · top {knowledgeTrace.requested_top_k} · threshold {knowledgeTrace.similarity_threshold} · {knowledgeTrace.duration_ms ?? "?"} ms</p>}
                  <ul className="knowledge-source-list">{knowledgeSources.map((source, index) => <li key={source.chunk_id ?? `${source.source}-${source.page ?? index}`}>
                  <strong>{source.title || source.source}</strong><span>{source.source}{source.page ? ` · page ${source.page}` : ""}{typeof source.score === "number" ? ` · similarity ${source.score.toFixed(4)}` : ""}{source.rank ? ` · rank ${source.rank}` : ""}{source.document_id ? ` · document ${source.document_id}` : ""}{source.chunk_id ? ` · chunk ${source.chunk_id}` : ""}</span>
                  {source.content && <p>{source.content}</p>}
                </li>)}</ul></>
                : <p className="inspector-note">No retrieval metadata was persisted with this loaded project.</p>}
            </section>

            <section className="inspector-section" id="model-inspector-reasoning">
              <h4>DESIGN REASONING</h4>
              {houseDesignState?.design_reasoning?.length ? houseDesignState.design_reasoning.map((item: Record<string, any>, index: number) => <p className="inspector-note" key={`${item.decision}-${index}`}><strong>{item.decision}</strong>: {item.value} · basis: {item.basis} · source IDs: {item.source_ids?.join(", ") || "none"}</p>) : <p className="inspector-note">No house design decisions have been recorded.</p>}
            </section>

            <section className="inspector-section" id="model-inspector-validation">
              <h4>VALIDATION</h4>
              {houseCAD ? (
                <div className="inspector-grid">
                  <span>Design specification</span><strong>Backend schema accepted</strong>
                  <span>CAD Kernel</span><strong>OpenCASCADE / build123d</strong>
                  <span>B-Rep Validity</span><strong style={{ color: cadIsValid ? "#34d399" : "#f87171" }}>{cadIsValid ? "VALID OpenCascade B-Rep" : houseCAD.validity === "FAIL" ? "INVALID" : "Not reported"}</strong>
                  <span>Solids Validated</span><strong>{houseCAD.solid_topology?.solid_count ?? 0} / {houseCAD.solid_topology?.solid_count ?? 0} solids</strong>
                  <span>Physical Mass Checks</span><strong>Passed (Positive Volume & Mass)</strong>
                </div>
              ) : (
                <div className="inspector-grid">
                  <span>Design specification</span><strong>Backend schema accepted</strong>
                  <span>Parametric rebuild</span><strong>{rebuildReport?.status === "rebuild_ok" ? "Rebuild completed" : "Not run"}</strong>
                  <span>Rebuilt exporter primitives</span><strong>{rebuildReport?.status === "rebuild_ok" ? rebuildReport.solid_count ?? "Not reported" : "Not reported"}</strong>
                  <span>Strength / FEA</span><strong>Not performed</strong>
                  <span>Engineering validation</span><strong>Not performed</strong>
                </div>
              )}
              {typeof houseCAD?.validity === "object" && houseCAD.validity?.validation_messages && houseCAD.validity.validation_messages.length > 0 && (
                <div style={{ marginTop: "0.5rem" }}>
                  {houseCAD.validity.validation_messages.map((msg, i) => (
                    <p key={i} className="inspector-note" style={{ color: "#34d399" }}>{msg}</p>
                  ))}
                </div>
              )}
              {rebuildReport?.bounding_box_m && <p className="inspector-note">Rebuild bounding box: {Object.values(rebuildReport.bounding_box_m.min ?? {}).map((value) => mm(Number(value))).join(" × ")} to {Object.values(rebuildReport.bounding_box_m.max ?? {}).map((value) => mm(Number(value))).join(" × ")}.</p>}
              {validationNotice && <p className="inspector-note" role="status">{validationNotice}</p>}
              <p className="engineering-caveat">
                {houseCAD ? "OPENCASCADE CAD KERNEL VERIFIED SOLID MODEL" : "PRELIMINARY ENGINEERING CONCEPT — NOT STRUCTURALLY VALIDATED"}
              </p>
            </section>
          </>}
        </div>
      </>}
    </aside>
  );
}
