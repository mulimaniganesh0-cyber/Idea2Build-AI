import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { API_BASE_URL, exportSTEP, getProjectSession, listProjects, rebuildValidate, sendChatMessage, exportHouseCADStep, exportHouseCADStl, exportHouseCADObj, generateHouseCAD, type HouseStateRequest } from "./api";
import { ModelViewport } from "./ModelViewport";
import { ModelInspector } from "./ModelInspector";
import { HouseDesignStudio } from "./HouseDesignStudio";
import { exportGeometryToOBJ } from "./utils/exportObj";
import type {
  CadFileItem,
  ChatMessage,
  DatasetMetric,
  DesignSpec,
  ParametricGeometry,
  SidebarRoute,
  Unit,
  UserPreferences,
  ViewMode,
  ProjectPlan,
} from "./types";

const QUICK_SUGGESTIONS = [
  { icon: "🏠", title: "Design a two-story house", prompt: "a house for 30*40 site with 2 story" },
  { icon: "🌉", title: "Design a pedestrian bridge", prompt: "Design a pedestrian bridge over a 50m span." },
  { icon: "⚙️", title: "Design a machine component", prompt: "Create a 500mm steel shaft with 40mm diameter" },
  { icon: "📐", title: "Create 3D primitive box", prompt: "Create a box 5m x 3m x 2m" },
  { icon: "🏗️", title: "Analyze engineering drawing", prompt: "Analyze the uploaded structural drawing for a 2-storey house." },
];

const MOCK_FILES: CadFileItem[] = [
  { id: "f1", name: "house_30x40_2story_spec.json", type: "JSON", size: "14.2 KB", updatedAt: "Just now" },
  { id: "f2", name: "house_architectural_drawing.dwg", type: "DWG", size: "2.4 MB", updatedAt: "Today, 14:20" },
  { id: "f3", name: "pedestrian_bridge_50m.step", type: "STEP", size: "8.1 MB", updatedAt: "Yesterday" },
  { id: "f4", name: "shaft_500mm_steel.stl", type: "STL", size: "1.2 MB", updatedAt: "3 days ago" },
];

const MOCK_DATASETS: DatasetMetric[] = [
  { domain: "Architectural Civil", sampleCount: 1420, avgConfidence: "98.4%", supportedPrimitives: ["House", "Site Plot", "Floor Slab", "Wall Envelope", "Roof"] },
  { domain: "Structural Bridges", sampleCount: 890, avgConfidence: "96.8%", supportedPrimitives: ["Deck Slab", "Steel Girder", "Truss", "Abutment Support"] },
  { domain: "Mechanical Engineering", sampleCount: 3250, avgConfidence: "99.1%", supportedPrimitives: ["Shaft", "Box", "Cylinder", "Plate", "Sphere", "Cone", "Hole"] },
];

export default function App() {
  // Hash Routing State
  const [currentRoute, setCurrentRoute] = useState<SidebarRoute>(() => {
    const hash = window.location.hash.replace("#", "");
    if (["home", "chat", "files", "viewer", "dataset", "settings"].includes(hash)) {
      return hash as SidebarRoute;
    }
    return "chat";
  });

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  // Project & CAD state
  const [projectId, setProjectId] = useState<string | null>(null);
  const [recentProjects, setRecentProjects] = useState<ProjectPlan[]>([]);
  const [isLoadingProject, setIsLoadingProject] = useState(false);
  const [designSpec, setDesignSpec] = useState<DesignSpec | null>(null);
  const [geometry, setGeometry] = useState<ParametricGeometry | null>(null);
  const [parametricJson, setParametricJson] = useState<Record<string, unknown> | null>(null);
  const [knowledgeStatus, setKnowledgeStatus] = useState<string | null>(null);
  const [knowledgeSources, setKnowledgeSources] = useState<Array<{ document_id?: number; chunk_id?: number; rank?: number; source: string; title?: string; page?: number | null; score?: number; content?: string }>>([]);
  const [knowledgeTrace, setKnowledgeTrace] = useState<{ trace_id: string; embedding_model: string; embedding_dimension: number | null; requested_top_k: number; similarity_threshold: number; duration_ms?: number } | null>(null);
  const [validationNotice, setValidationNotice] = useState<string | null>(null);
  const [rebuildReport, setRebuildReport] = useState<{ status?: string; solid_count?: number; feature_count?: number; bounding_box_m?: { min?: { x?: number; y?: number; z?: number }; max?: { x?: number; y?: number; z?: number } } } | null>(null);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [houseCADData, setHouseCADData] = useState<Record<string, unknown> | null>(null);
  const [kernelReport, setKernelReport] = useState<Record<string, unknown> | null>(null);
  const [houseDesignState, setHouseDesignState] = useState<Record<string, any> | null>(null);

  // Chat & Input state
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastFailedInput, setLastFailedInput] = useState<string | null>(null);

  // Viewport controls
  const [showGrid, setShowGrid] = useState(true);
  const [showAxes, setShowAxes] = useState(true);
  const [resetKey, setResetKey] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("exterior");
  const [activeFloor, setActiveFloor] = useState<number | null>(null);

  // User Settings
  const [preferences, setPreferences] = useState<UserPreferences>({
    defaultUnit: "ft",
    renderShadows: true,
    showGridDefault: true,
    showAxesDefault: true,
    apiUrl: API_BASE_URL,
  });

  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void refreshProjects();
    const savedProjectId = sessionStorage.getItem("ai-cad-active-project-id");
    if (savedProjectId) void loadProjectSession(savedProjectId);
  }, []);

  useEffect(() => {
    if (projectId) sessionStorage.setItem("ai-cad-active-project-id", projectId);
    else sessionStorage.removeItem("ai-cad-active-project-id");
  }, [projectId]);
  // Listen to window.location.hash & popstate for browser Back/Forward navigation
  useEffect(() => {
    const syncRouteFromHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (["home", "chat", "files", "viewer", "dataset", "settings"].includes(hash)) {
        setCurrentRoute(hash as SidebarRoute);
      } else if (!hash) {
        setCurrentRoute("chat");
      }
    };

    window.addEventListener("hashchange", syncRouteFromHash);
    window.addEventListener("popstate", syncRouteFromHash);
    return () => {
      window.removeEventListener("hashchange", syncRouteFromHash);
      window.removeEventListener("popstate", syncRouteFromHash);
    };
  }, []);

  function navigateTo(route: SidebarRoute) {
    setCurrentRoute(route);
    window.location.hash = route;
    setIsSidebarOpen(false);
  }

  // Handle ESC key to exit fullscreen viewer back to chat workspace
  useEffect(() => {
    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape" && currentRoute === "viewer") {
        navigateTo("chat");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentRoute]);

  // Auto-scroll chat to latest message
  useEffect(() => {
    if (currentRoute === "chat") {
      chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isProcessing, currentRoute]);

  async function refreshProjects() {
    try {
      setRecentProjects(await listProjects());
    } catch {
      // The workspace remains usable if the project API is offline.
    }
  }

  async function loadProjectSession(id: string) {
    setIsLoadingProject(true);
    try {
      const session = await getProjectSession(id);
      setProjectId(session.plan.project_id);
      setDesignSpec(session.design_state);
      setGeometry(session.geometry);
      setParametricJson(session.parametric_json ?? null);
      setHouseCADData(session.kernel_report ?? null);
      setKernelReport(null);
      setHouseDesignState(session.house_design_state ?? null);
      setKnowledgeStatus((session.house_design_state?.knowledge_status as string | undefined) ?? null);
      setKnowledgeSources((session.house_design_state?.knowledge_provenance as Array<{ source: string; title?: string; page?: number | null; score?: number; content?: string }> | undefined) ?? []);
      setRebuildReport(null);
      setMessages(session.messages.map((message, index) => ({
        id: `saved_${index}`,
        role: message.role,
        text: message.text,
        timestamp: new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      })));
      setKnowledgeStatus(null);
      setKnowledgeSources([]);
      navigateTo("chat");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not load this project.");
    } finally {
      setIsLoadingProject(false);
    }
  }

  function startNewProject() {
    if (isProcessing || isLoadingProject) return;
    setProjectId(null);
    setDesignSpec(null);
    setGeometry(null);
    setParametricJson(null);
    setRebuildReport(null);
    setHouseCADData(null);
    setMessages([]);
    setKnowledgeStatus(null);
    setKnowledgeSources([]);
    setValidationNotice(null);
    setErrorMessage(null);
    navigateTo("chat");
  }
  async function handleSend(promptText: string) {
    const text = promptText.trim();
    if (!text || isProcessing) return;

    navigateTo("chat");
    setErrorMessage(null);
    setLastFailedInput(null);

    const userMessage: ChatMessage = {
      id: `user_${Date.now()}`,
      role: "user",
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsProcessing(true);

    try {
      const response = await sendChatMessage(text, projectId);

      if (response.project_id) setProjectId(response.project_id);
      if (response.design_state) {
        setDesignSpec(response.design_state);
        const params = response.design_state.feature_parameters || {};
        if (params.view_mode && typeof params.view_mode === "string") {
          setViewMode(params.view_mode as ViewMode);
        }
        if (params.active_floor !== undefined && Number(params.active_floor) >= 0) {
          setActiveFloor(Number(params.active_floor));
        } else if (params.active_floor === -1) {
          setActiveFloor(null);
        }
      }
      if (response.geometry) setGeometry(response.geometry);
      if (response.design_state) setParametricJson(response.parametric_json ?? null);
      setKnowledgeStatus(response.knowledge_status ?? response.house_design_state?.knowledge_status as string ?? null);
      setKnowledgeSources(response.knowledge_sources ?? response.house_design_state?.knowledge_provenance as Array<{ source: string; title?: string; page?: number | null; score?: number; content?: string }> ?? []);
      setKnowledgeTrace(response.knowledge_trace ?? response.house_design_state?.knowledge_trace as typeof knowledgeTrace ?? null);
      setValidationNotice(null);
      setRebuildReport(null);
      setHouseCADData(response.kernel_report ?? null);
      setKernelReport(response.design_state?.object_type === "house" ? null : response.kernel_report ?? null);
      setHouseDesignState(response.house_design_state ?? null);

      // Auto-fetch real OpenCASCADE CAD data for house designs
      if (response.design_state?.object_type === "house" && response.design_state.feature_parameters && !response.kernel_report) {
        const fp = response.design_state.feature_parameters;
        const houseReq: HouseStateRequest = {
          project_id: response.project_id,
          site_width_m: typeof fp.site_width_m === "number" ? fp.site_width_m : null,
          site_length_m: typeof fp.site_length_m === "number" ? fp.site_length_m : null,
          floors: typeof fp.floors === "number" ? Math.round(fp.floors) : 2,
          building_width_m: typeof fp.building_width_m === "number" ? fp.building_width_m : null,
          building_length_m: typeof fp.building_length_m === "number" ? fp.building_length_m : null,
          floor_height_m: typeof fp.floor_height_m === "number" ? fp.floor_height_m : 3.0,
          material: "reinforced_concrete",
          roof_type: typeof fp.roof_type === "string" ? fp.roof_type : "pitched",
        };
        generateHouseCAD(houseReq).then(setHouseCADData).catch(() => { /* non-blocking */ });
      }

      const assistantMessage: ChatMessage = {
        id: `assistant_${Date.now()}`,
        role: "assistant",
        text: response.message,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        questions: response.questions,
        suggestions: response.suggestions,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      void refreshProjects();
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Failed to connect to the CAD backend.";
      setErrorMessage(errMsg);
      setLastFailedInput(text);

      const errorChatMsg: ChatMessage = {
        id: `err_${Date.now()}`,
        role: "assistant",
        text: `⚠️ Request failed: ${errMsg}`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        isError: true,
      };
      setMessages((prev) => [...prev, errorChatMsg]);
    } finally {
      setIsProcessing(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void handleSend(input);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend(input);
    }
  }

  function handleBackToProjects() {
    if (messages.length > 0 && isProcessing) {
      if (!window.confirm("A design request is currently processing. Are you sure you want to return to projects?")) {
        return;
      }
    }
    navigateTo("home");
  }

async function validateDesign() {
    if (!parametricJson) return;
    setValidationNotice("Rebuilding the parametric CAD source…");
    try {
      const result = await rebuildValidate(parametricJson);
      setRebuildReport(result);
      setValidationNotice(result.status === "rebuild_ok"
        ? `Parametric rebuild completed · ${result.solid_count} exporter box primitives · ${result.feature_count} feature definitions`
        : `Validation returned ${result.status || "an unknown status"}`);
    } catch (error) {
      setValidationNotice(error instanceof Error ? error.message : "CAD validation failed.");
    }
  }

  async function exportStepFile() {
    if (!parametricJson && !houseCADData) return;
    try {
      const isHouse = designSpec?.object_type === "house";
      if (isHouse && designSpec?.feature_parameters) {
        const fp = designSpec.feature_parameters;
        const houseReq: HouseStateRequest = {
          project_id: projectId ?? "unknown",
          site_width_m: typeof fp.site_width_m === "number" ? fp.site_width_m : null,
          site_length_m: typeof fp.site_length_m === "number" ? fp.site_length_m : null,
          floors: typeof fp.floors === "number" ? Math.round(fp.floors) : 2,
          building_width_m: typeof fp.building_width_m === "number" ? fp.building_width_m : null,
          building_length_m: typeof fp.building_length_m === "number" ? fp.building_length_m : null,
          floor_height_m: typeof fp.floor_height_m === "number" ? fp.floor_height_m : 3.0,
          material: "reinforced_concrete",
          roof_type: typeof fp.roof_type === "string" ? fp.roof_type : "pitched",
        };
        const blob = await exportHouseCADStep(houseReq);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `house-${Math.round(fp.floors as number) || 2}floors-${projectId?.slice(0, 8) || "export"}.step`;
        link.click();
        URL.revokeObjectURL(url);
      } else if (parametricJson) {
        const blob = await exportSTEP(parametricJson);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${designSpec?.object_type || "design"}-${projectId || "export"}.step`;
        link.click();
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      setValidationNotice(error instanceof Error ? error.message : "STEP export failed.");
    }
  }

  function exportSpecJson() {
    if (!designSpec) return;
    const blob = new Blob([JSON.stringify({ projectId, designSpec, geometry }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `design-spec-${projectId || "export"}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function exportObjFile() {
    if (!geometry || !geometry.components || geometry.components.length === 0) {
      alert("No 3D CAD geometry components available to export.");
      return;
    }

    let objContent = `# AI-CAD Engineer Wavefront OBJ File\n# Project: ${projectId || "design"}\n# Object Type: ${designSpec?.object_type || "cad_model"}\n\n`;
    let vertexOffset = 1;

    for (const comp of geometry.components) {
      const [px, py, pz] = comp.position_m || [0, 0, 0];
      const [dx, dy, dz] = comp.dimensions_m;
      const [rx, ry, rz] = comp.rotation_rad || [0, 0, 0];
      const hx = dx / 2;
      const hy = dy / 2;
      const hz = dz / 2;

      // 8 local corners of the box
      const corners = [
        [-hx, -hy, -hz],
        [hx, -hy, -hz],
        [hx, hy, -hz],
        [-hx, hy, -hz],
        [-hx, -hy, hz],
        [hx, -hy, hz],
        [hx, hy, hz],
        [-hx, hy, hz],
      ];

      objContent += `o ${comp.name.replace(/[^a-zA-Z0-9_]/g, "_")}\n`;

      // Transform corners by Euler rotation and translation
      for (const [x, y, z] of corners) {
        // Apply X rotation
        let y1 = y * Math.cos(rx) - z * Math.sin(rx);
        let z1 = y * Math.sin(rx) + z * Math.cos(rx);
        let x1 = x;

        // Apply Y rotation
        let x2 = x1 * Math.cos(ry) + z1 * Math.sin(ry);
        let z2 = -x1 * Math.sin(ry) + z1 * Math.cos(ry);
        let y2 = y1;

        // Apply Z rotation
        let x3 = x2 * Math.cos(rz) - y2 * Math.sin(rz);
        let y3 = x2 * Math.sin(rz) + y2 * Math.cos(rz);
        let z3 = z2;

        objContent += `v ${(x3 + px).toFixed(4)} ${(y3 + py).toFixed(4)} ${(z3 + pz).toFixed(4)}\n`;
      }

      // 6 quad faces
      const faces = [
        [1, 2, 3, 4], // Back
        [5, 8, 7, 6], // Front
        [1, 5, 6, 2], // Bottom
        [4, 3, 7, 8], // Top
        [1, 4, 8, 5], // Left
        [2, 6, 7, 3], // Right
      ];

      for (const f of faces) {
        objContent += `f ${f[0] + vertexOffset - 1} ${f[1] + vertexOffset - 1} ${f[2] + vertexOffset - 1} ${f[3] + vertexOffset - 1}\n`;
      }
      vertexOffset += 8;
      objContent += "\n";
    }

    const floors = designSpec?.feature_parameters?.floors || designSpec?.feature_parameters?.floor_count;
    const filename = designSpec?.object_type === "house"
      ? `house-${floors || 2}floors-rev01.obj`
      : designSpec?.object_type === "bridge"
      ? `bridge-${designSpec?.feature_parameters?.bridge_type || "concept"}-rev01.obj`
      : `${designSpec?.object_type || "model"}-rev01.obj`;

    const blob = new Blob([objContent], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  // Render view depending on active currentRoute
  return (
    <div className={`workspace-layout ${theme}`}>
      {/* Top Header */}
      <header className="workspace-header">
        <div className="header-left">
          <button className="mobile-menu-btn" onClick={() => setIsSidebarOpen((o) => !o)} title="Toggle menu">
            ☰
          </button>
          <div className="logo-brand" onClick={() => navigateTo("home")} style={{ cursor: "pointer" }}>
            <span className="logo-icon">◈</span>
            <span className="logo-title">AI-CAD Engineer</span>
          </div>
          <div className="header-divider" />
          <button className="btn-back" onClick={handleBackToProjects} title="Return to Projects Catalog">
            ← Back to Projects
          </button>
        </div>

        <div className="header-center">
          <span className="project-title">
            {designSpec ? ((recentProjects.find((project) => project.project_id === projectId)?.summary ?? "").match(/^(Unspecified|Mechanical) request classified at complexity level/i) ? designSpec.object_type : (recentProjects.find((project) => project.project_id === projectId)?.summary || `${designSpec.object_type} design`)).toUpperCase() : "NEW CAD PROJECT"}
          </span>
          {designSpec && <div className="engineering-state-badges" aria-label="Engineering model status"><span>MODEL GENERATED</span><span>STRENGTH NOT ANALYZED</span></div>}
          <span className="save-status">● Server project ({projectId ? projectId.slice(0, 8) : "Not saved yet"})</span>
        </div>

        <div className="header-right">
          <button className="btn-tool" onClick={startNewProject} disabled={isProcessing || isLoadingProject}>New Project</button>
          {validationNotice && <span className="save-status" role="status">{validationNotice}</span>}
          <button className="btn-tool" onClick={() => void validateDesign()} disabled={!parametricJson} title="Reconstruct the parametric export primitives and report their bounds">Rebuild Check</button>
          <button className="btn-tool" onClick={() => void exportStepFile()} disabled={!parametricJson} title="Export backend STEP geometry">Export STEP</button>
          <button className="theme-toggle" onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}>
            {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
          </button>
          <div className="user-profile">
            <span className="avatar">ENG</span>
            <span className="user-role">Lead Engineer</span>
          </div>
        </div>
      </header>

      <div className="workspace-body">
        {/* Left Sidebar Navigation */}
        <aside className={`workspace-sidebar ${isSidebarOpen ? "open" : ""}`}>
          <nav className="sidebar-nav">
            <button className={`nav-item ${currentRoute === "home" ? "active" : ""}`} onClick={() => navigateTo("home")}>
              <span className="nav-icon">🏠</span>
              <span className="nav-label">Projects</span>
            </button>

            <button className={`nav-item ${currentRoute === "chat" ? "active" : ""}`} onClick={() => navigateTo("chat")}>
              <span className="nav-icon">💬</span>
              <span className="nav-label">Design Studio</span>
            </button>

            <button className={`nav-item ${currentRoute === "files" ? "active" : ""}`} onClick={() => navigateTo("files")}>
              <span className="nav-icon">📁</span>
              <span className="nav-label">Files & Exports</span>
            </button>

            <button className={`nav-item ${currentRoute === "viewer" ? "active" : ""}`} onClick={() => navigateTo("viewer")}>
              <span className="nav-icon">🧊</span>
              <span className="nav-label">3D Viewer</span>
            </button>

            <button className={`nav-item ${currentRoute === "dataset" ? "active" : ""}`} onClick={() => navigateTo("dataset")}>
              <span className="nav-icon">📊</span>
              <span className="nav-label">Learning Center</span>
            </button>

            <button className={`nav-item ${currentRoute === "settings" ? "active" : ""}`} onClick={() => navigateTo("settings")}>
              <span className="nav-icon">⚙️</span>
              <span className="nav-label">Settings</span>
            </button>
          </nav>

          <div className="sidebar-footer">
            <span className="sys-status">CAD Engine 0.1.0 · Online</span>
          </div>
        </aside>

        {/* Dynamic Route Content */}
        <main className="workspace-content">
          {/* HOME / LANDING ROUTE */}
          {currentRoute === "home" && (
            <div className="route-page home-page">
              <section className="home-hero">
                <span className="hero-badge">AI-CAD PARAMETRIC STUDIO</span>
                <h1>What engineering model would you like to design today?</h1>
                <p>Describe your idea in natural language — e.g. <i>"a house for 30×40 site with 2 story"</i> — and receive a preliminary 3D model beside the conversation.</p>

                <form className="home-input-card" onSubmit={handleSubmit}>
                  <textarea
                    autoFocus
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Describe your design request…&#10;&#10;Examples:&#10;• a house for 30*40 site with 2 story&#10;• Design a pedestrian bridge over a 50m span&#10;• Create a 500mm steel shaft with 40mm diameter"
                    rows={4}
                  />
                  <div className="card-footer">
                    <span className="hint-text">Press Enter to send · Shift+Enter for newline</span>
                    <button type="submit" disabled={!input.trim()} className="btn-primary">
                      Start Designing →
                    </button>
                  </div>
                </form>

                {recentProjects.length > 0 && (
                  <section className="recent-projects-section" aria-label="My Projects">
                    <h3>My Projects</h3>
                    <div className="recent-projects-grid">
                      {recentProjects.map((project) => (
                        <button key={project.project_id} className="recent-project-card" onClick={() => void loadProjectSession(project.project_id)}>
                          <strong>{project.summary || project.source_prompt}</strong>
                          <span>{project.domain} · revision {project.version}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                )}                <div className="quick-suggestions-section">
                  <h3>Or pick a template:</h3>
                  <div className="template-grid">
                    {QUICK_SUGGESTIONS.map((item) => (
                      <div key={item.title} className="template-card" onClick={() => void handleSend(item.prompt)}>
                        <span className="card-icon">{item.icon}</span>
                        <h4>{item.title}</h4>
                        <p>{item.prompt}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            </div>
          )}

          {/* CHAT & DESIGN ROUTE (Integrated 4-Column Layout) */}
          {currentRoute === "chat" && (
            <div className={`route-page chat-design-page ${inspectorCollapsed ? "inspector-collapsed" : ""}`}>
              {/* Column 1: Chat Panel */}
              <section className="chat-section">
                <div className="chat-header">
                  <h2>AI Engineer</h2>
                  <p>Describe what you want to build, refine, or understand.</p>
                </div>

                <div className="messages-scroll">
                  {messages.length === 0 && (
                    <div className="chat-welcome">
                      <span>◈</span>
                      <h3>Start Your Design</h3>
                      <p>Enter a prompt below or click a suggestion to build a 3D model.</p>
                      <div className="pills-flex">
                        {QUICK_SUGGESTIONS.map((s) => (
                          <button key={s.title} className="btn-pill" onClick={() => void handleSend(s.prompt)}>
                            {s.icon} {s.title}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {messages.map((msg) => (
                    <div key={msg.id} className={`message-bubble ${msg.role} ${msg.isError ? "error" : ""}`}>
                      <div className="bubble-header">
                        <span className="sender">{msg.role === "assistant" ? "AI-CAD Engineer" : "You"}</span>
                        <span className="timestamp">{msg.timestamp}</span>
                      </div>
                      <div className="bubble-content">{msg.text}</div>

                      {msg.questions && msg.questions.length > 0 && (
                        <div className="questions-box">
                          <strong>Clarification Questions:</strong>
                          <ul>
                            {msg.questions.map((q) => (
                              <li key={q}>{q}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {msg.suggestions && msg.suggestions.length > 0 && (
                        <div className="suggestions-list">
                          {msg.suggestions.map((s) => (
                            <button key={s} className="btn-suggestion" onClick={() => void handleSend(s)}>
                              {s}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}

                  {isProcessing && (
                    <div className="message-bubble assistant loading">
                      <div className="bubble-header">
                        <span className="sender">AI-CAD Engineer</span>
                      </div>
                      <div className="loading-dots">
                        <span />
                        <span />
                        <span />
                      </div>
                      <p className="loading-text">Extracting requirements & generating CAD geometry…</p>
                    </div>
                  )}

                  <div ref={chatEndRef} />
                </div>

                {errorMessage && (
                  <div className="chat-error-banner">
                    <span>⚠️ {errorMessage}</span>
                    {lastFailedInput && (
                      <button className="btn-retry" onClick={() => void handleSend(lastFailedInput)}>
                        🔄 Retry
                      </button>
                    )}
                  </div>
                )}

                <form className="chat-composer" onSubmit={handleSubmit}>
                  <textarea
                    aria-label="Design prompt input"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={designSpec ? "Request a modification, e.g. 'Add another floor' or 'Make it 6m long'" : "Type your design request…"}
                    rows={3}
                  />
                  <div className="composer-toolbar">
                    <span className="shortcut-hint">Enter to send · Shift+Enter for newline</span>
                    <button type="submit" disabled={isProcessing || !input.trim()} className="btn-send">
                      Send Prompt ↑
                    </button>
                  </div>
                </form>
              </section>

              {/* Column 2: 3D Viewport */}
              <section className="viewport-section">
                <div className="viewport-toolbar">
                  <div className="toolbar-left">
                    <span className="viewport-title">3D VIEWPORT</span>
                    {geometry && <span className="component-count">{geometry.components.length} Components</span>}
                  </div>

                  <div className="toolbar-actions">
                    {designSpec?.object_type === "house" && (
                      <>
                        <div className="view-mode-group" style={{ display: "flex", gap: "4px", marginRight: "4px" }}>
                          <button
                            className={`btn-tool ${viewMode === "exterior" ? "active" : ""}`}
                            onClick={() => setViewMode("exterior")}
                            title="Exterior Massing View"
                          >
                            🏢 Ext
                          </button>
                          <button
                            className={`btn-tool ${viewMode === "interior" ? "active" : ""}`}
                            onClick={() => setViewMode("interior")}
                            title="Interior Rooms & Furniture"
                          >
                            🛋️ Int
                          </button>
                          <button
                            className={`btn-tool ${viewMode === "cutaway" ? "active" : ""}`}
                            onClick={() => setViewMode("cutaway")}
                            title="Cutaway 3D Section"
                          >
                            ✂️ Cut
                          </button>
                          <button
                            className={`btn-tool ${viewMode === "floor_plan" ? "active" : ""}`}
                            onClick={() => setViewMode("floor_plan")}
                            title="Top-down Floor Plan"
                          >
                            📐 Plan
                          </button>
                        </div>

                        {/* Floor Level Filter */}
                        <div className="floor-filter-group" style={{ display: "flex", gap: "2px", marginRight: "6px" }}>
                          <button
                            className={`btn-tool btn-xs ${activeFloor === null ? "active" : ""}`}
                            onClick={() => setActiveFloor(null)}
                            title="View All Floors"
                          >
                            All
                          </button>
                          {Array.from({
                            length: Math.max(
                              1,
                              Number(designSpec?.feature_parameters?.floors || designSpec?.feature_parameters?.floor_count || 2)
                            ),
                          }).map((_, idx) => (
                            <button
                              key={idx}
                              className={`btn-tool btn-xs ${activeFloor === idx ? "active" : ""}`}
                              onClick={() => {
                                setActiveFloor(idx);
                                if (viewMode === "exterior") setViewMode("interior");
                              }}
                              title={`Isolate Floor Level ${idx} (${idx === 0 ? "Ground Floor" : `${idx}F`})`}
                            >
                              {idx === 0 ? "L0" : `L${idx}`}
                            </button>
                          ))}
                        </div>
                      </>
                    )}

                    <button className="btn-tool" onClick={() => setResetKey((k) => k + 1)} title="Fit Camera">
                      🎯 Fit
                    </button>
                    <button className="btn-tool" onClick={() => setResetKey((k) => k + 1)} title="Reset Camera">
                      🔄 Reset
                    </button>
                    <button className={`btn-tool ${showGrid ? "active" : ""}`} onClick={() => setShowGrid((g) => !g)} title="Toggle Grid">
                      🌐 Grid
                    </button>
                    <button className={`btn-tool ${showAxes ? "active" : ""}`} onClick={() => setShowAxes((a) => !a)} title="Toggle Axes">
                      📐 Axes
                    </button>
                    <button
                      className="btn-tool"
                      onClick={() => exportGeometryToOBJ(geometry, designSpec, `cad_${designSpec?.object_type || "model"}.obj`)}
                      title="Export 3D Model as Wavefront OBJ"
                    >
                      💾 OBJ
                    </button>
                    <button
                      className="btn-tool highlight-tool"
                      onClick={() => navigateTo("viewer")}
                      title="Open Fullscreen 3D Inspector"
                    >
                      ⛶ Fullscreen
                    </button>
                  </div>
                </div>

                <div className="viewport-canvas-wrapper">
                  <ModelViewport
                    design={designSpec}
                    geometry={geometry}
                    showGrid={showGrid}
                    showAxes={showAxes}
                    theme={theme}
                    viewMode={viewMode}
                    activeFloor={activeFloor}
                    resetKey={resetKey}
                    isLoading={isProcessing}
                    error={errorMessage}
                  />
                  {designSpec && <div className="viewport-model-hud" aria-label="Model information">
                    <strong>{designSpec.object_type.replaceAll("_", " ").toUpperCase()}</strong>
                    <span>{designSpec.dimensions.length} × {designSpec.dimensions.width} × {designSpec.dimensions.height} {designSpec.unit}</span>
                    <span>{geometry?.components.length ?? 0} backend components · {designSpec.material || "Material not specified"}</span>
                    <span>Strength analysis · Not analyzed</span>
                  </div>}
                </div>
              </section>

              <ModelInspector
                designSpec={designSpec}
                geometry={geometry}
                parametricJson={parametricJson}
                projectName={recentProjects.find((project) => project.project_id === projectId)?.summary ?? null}
                projectId={projectId}
                knowledgeStatus={knowledgeStatus}
                knowledgeSources={knowledgeSources}
                knowledgeTrace={knowledgeTrace}
                rebuildReport={rebuildReport}
                validationNotice={validationNotice}
                collapsed={inspectorCollapsed}
                onToggleCollapsed={() => setInspectorCollapsed((value) => !value)}
                houseCADData={houseCADData}
                kernelReport={kernelReport}
                houseDesignState={houseDesignState}
              />
              {designSpec?.object_type === "house" && <HouseDesignStudio projectId={projectId} onProjectId={(id) => setProjectId(id)} onGenerated={(data) => {
                setProjectId(data.project_id);
                setDesignSpec(data.design_state);
                setGeometry(data.geometry);
                setHouseCADData(data.kernel_report);
                setHouseDesignState(data.house_design_state);
                setParametricJson(data.parametric_json ?? null);
                setKnowledgeStatus(data.knowledge?.status ?? "NOT_REQUIRED");
                setKnowledgeSources(data.knowledge?.sources ?? []);
                setKnowledgeTrace(data.knowledge?.trace ?? null);
                setKernelReport(null);
                void refreshProjects();
              }} />}
            </div>
          )}

          {/* FILES & CAD ROUTE */}
          {currentRoute === "files" && (
            <div className="route-page files-page">
              <div className="page-header">
                <h2>Files & CAD Assets</h2>
                <p>Manage project specifications, exported 3D geometry files, and uploaded drawings.</p>
              </div>

              <div className="files-table-card">
                <div className="table-toolbar">
                  <span className="count">{MOCK_FILES.length} Files Available</span>
                  <button className="btn-action" onClick={() => alert("Upload file capability ready.")}>
                    📤 Upload Drawing / File
                  </button>
                </div>

                <table className="files-table">
                  <thead>
                    <tr>
                      <th>FILE NAME</th>
                      <th>TYPE</th>
                      <th>SIZE</th>
                      <th>UPDATED</th>
                      <th>ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {MOCK_FILES.map((file) => (
                      <tr key={file.id}>
                        <td className="file-name">📄 {file.name}</td>
                        <td><span className="badge-type">{file.type}</span></td>
                        <td>{file.size}</td>
                        <td>{file.updatedAt}</td>
                        <td>
                          <button className="btn-sm" onClick={() => alert(`Downloading ${file.name}...`)}>
                            Download
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 3D VIEWER ROUTE (Immersive Fullscreen View) */}
          {currentRoute === "viewer" && (
            <div className="route-page viewer-page">
              <div className="fullscreen-viewer-wrapper">
                <div className="viewer-toolbar fullscreen-header">
                  <div className="toolbar-left">
                    <button
                      className="btn-back-workspace"
                      onClick={() => navigateTo("chat")}
                      title="Return to Chat Workspace"
                    >
                      ← Back to Workspace
                    </button>
                    <span className="viewport-title">FULLSCREEN 3D MODEL INSPECTOR</span>
                    {designSpec && (
                      <span className="badge-obj-type">
                        {designSpec.object_type.toUpperCase()}
                      </span>
                    )}
                    {geometry && (
                      <span className="component-count">
                        {geometry.components.length} Components
                      </span>
                    )}
                  </div>

                  <div className="toolbar-actions">
                    {designSpec?.object_type === "house" && (
                      <>
                        <div className="view-mode-group" style={{ display: "flex", gap: "4px", marginRight: "4px" }}>
                          <button
                            className={`btn-tool ${viewMode === "exterior" ? "active" : ""}`}
                            onClick={() => setViewMode("exterior")}
                            title="Exterior Massing View"
                          >
                            🏢 Exterior
                          </button>
                          <button
                            className={`btn-tool ${viewMode === "interior" ? "active" : ""}`}
                            onClick={() => setViewMode("interior")}
                            title="Interior Rooms & Furniture"
                          >
                            🛋️ Interior
                          </button>
                          <button
                            className={`btn-tool ${viewMode === "cutaway" ? "active" : ""}`}
                            onClick={() => setViewMode("cutaway")}
                            title="Cutaway 3D Section"
                          >
                            ✂️ Cutaway
                          </button>
                          <button
                            className={`btn-tool ${viewMode === "floor_plan" ? "active" : ""}`}
                            onClick={() => setViewMode("floor_plan")}
                            title="Top-down Floor Plan"
                          >
                            📐 Floor Plan
                          </button>
                        </div>

                        {/* Floor Selector */}
                        <div className="floor-filter-group" style={{ display: "flex", gap: "2px", marginRight: "6px" }}>
                          <button
                            className={`btn-tool btn-xs ${activeFloor === null ? "active" : ""}`}
                            onClick={() => setActiveFloor(null)}
                            title="View All Floors"
                          >
                            All Floors
                          </button>
                          {Array.from({
                            length: Math.max(
                              1,
                              Number(designSpec?.feature_parameters?.floors || designSpec?.feature_parameters?.floor_count || 2)
                            ),
                          }).map((_, idx) => (
                            <button
                              key={idx}
                              className={`btn-tool btn-xs ${activeFloor === idx ? "active" : ""}`}
                              onClick={() => {
                                setActiveFloor(idx);
                                if (viewMode === "exterior") setViewMode("interior");
                              }}
                              title={`Isolate Floor Level ${idx} (${idx === 0 ? "Ground Floor" : `${idx}F`})`}
                            >
                              {idx === 0 ? "L0 (Ground)" : `L${idx}`}
                            </button>
                          ))}
                        </div>
                      </>
                    )}

                    <button className="btn-tool" onClick={() => setResetKey((k) => k + 1)} title="Fit Camera">
                      🎯 Fit
                    </button>
                    <button className="btn-tool" onClick={() => setResetKey((k) => k + 1)} title="Reset Camera">
                      🔄 Reset
                    </button>
                    <button className={`btn-tool ${showGrid ? "active" : ""}`} onClick={() => setShowGrid((g) => !g)} title="Toggle Grid">
                      🌐 Grid
                    </button>
                    <button className={`btn-tool ${showAxes ? "active" : ""}`} onClick={() => setShowAxes((a) => !a)} title="Toggle Axes">
                      📐 Axes
                    </button>
                    <button
                      className="btn-tool"
                      onClick={() => exportGeometryToOBJ(geometry, designSpec, `cad_${designSpec?.object_type || "model"}.obj`)}
                      title="Export 3D Model as Wavefront OBJ"
                    >
                      💾 Download OBJ
                    </button>
                    <button
                      className="btn-tool btn-danger-exit"
                      onClick={() => navigateTo("chat")}
                      title="Exit Fullscreen (Esc)"
                    >
                      ✕ Exit
                    </button>
                  </div>
                </div>

                <div className="fullscreen-canvas-container" style={{ flex: 1, position: "relative", minHeight: 0 }}>
                  <ModelViewport
                    design={designSpec}
                    geometry={geometry}
                    showGrid={showGrid}
                    showAxes={showAxes}
                    theme={theme}
                    viewMode={viewMode}
                    activeFloor={activeFloor}
                    resetKey={resetKey}
                    isLoading={isProcessing}
                    error={errorMessage}
                  />
                  {designSpec && <div className="viewport-model-hud" aria-label="Model information">
                    <strong>{designSpec.object_type.replaceAll("_", " ").toUpperCase()}</strong>
                    <span>{designSpec.dimensions.length} × {designSpec.dimensions.width} × {designSpec.dimensions.height} {designSpec.unit}</span>
                    <span>{geometry?.components.length ?? 0} backend components · {designSpec.material || "Material not specified"}</span>
                    <span>Strength analysis · Not analyzed</span>
                  </div>}

                  {/* HUD Overlay in Fullscreen */}
                  <div className="fullscreen-hud">
                    <span><strong>Mode:</strong> {viewMode.toUpperCase()}</span>
                    {activeFloor !== null && <span><strong>Floor:</strong> Level {activeFloor}</span>}
                    {designSpec && (
                      <span>
                        <strong>Size:</strong> {(designSpec.dimensions_mm.length / 1000).toFixed(1)}m × {(designSpec.dimensions_mm.width / 1000).toFixed(1)}m × {(designSpec.dimensions_mm.height / 1000).toFixed(1)}m
                      </span>
                    )}
                    <span className="hud-hint">Press <kbd>ESC</kbd> to exit</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* DATASET ROUTE */}
          {currentRoute === "dataset" && (
            <div className="route-page dataset-page">
              <div className="page-header">
                <h2>Parametric Design Datasets</h2>
                <p>Trained domain models, boundary validation rules, and schema statistics.</p>
              </div>

              <div className="dataset-grid">
                {MOCK_DATASETS.map((ds) => (
                  <div key={ds.domain} className="dataset-card">
                    <span className="card-domain">{ds.domain}</span>
                    <div className="stat-row">
                      <span className="lbl">Samples</span>
                      <span className="val">{ds.sampleCount}</span>
                    </div>
                    <div className="stat-row">
                      <span className="lbl">Accuracy</span>
                      <span className="val highlight">{ds.avgConfidence}</span>
                    </div>
                    <div className="primitives-list">
                      <strong>Supported Primitives:</strong>
                      <div className="chips">
                        {ds.supportedPrimitives.map((p) => (
                          <span key={p} className="chip">{p}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SETTINGS ROUTE */}
          {currentRoute === "settings" && (
            <div className="route-page settings-page">
              <div className="page-header">
                <h2>CAD Engine Settings</h2>
                <p>Configure default units, rendering performance, and API endpoint base URLs.</p>
              </div>

              <div className="settings-card">
                <div className="setting-group">
                  <label>Default Dimension Unit System</label>
                  <select
                    value={preferences.defaultUnit}
                    onChange={(e) => setPreferences((p) => ({ ...p, defaultUnit: e.target.value as Unit }))}
                  >
                    <option value="ft">Feet (ft)</option>
                    <option value="m">Meters (m)</option>
                    <option value="mm">Millimeters (mm)</option>
                    <option value="cm">Centimeters (cm)</option>
                    <option value="in">Inches (in)</option>
                  </select>
                </div>

                <div className="setting-group checkbox">
                  <label>
                    <input
                      type="checkbox"
                      checked={preferences.renderShadows}
                      onChange={(e) => setPreferences((p) => ({ ...p, renderShadows: e.target.checked }))}
                    />
                    Enable Soft Shadows in 3D Viewport
                  </label>
                </div>

                <div className="setting-group">
                  <label>API Base URL Endpoint</label>
                  <input
                    type="text"
                    value={preferences.apiUrl}
                    onChange={(e) => setPreferences((p) => ({ ...p, apiUrl: e.target.value }))}
                  />
                </div>

                <button className="btn-primary" onClick={() => alert("Settings updated successfully.")}>
                  Save Preferences
                </button>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
