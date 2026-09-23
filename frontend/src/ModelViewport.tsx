import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { DesignSpec, GeometryComponent, ParametricGeometry, ViewMode } from "./types";
import { debugLog } from "./api";

interface Props {
  design: DesignSpec | null;
  geometry?: ParametricGeometry | null;
  showGrid?: boolean;
  showAxes?: boolean;
  theme?: "dark" | "light";
  viewMode?: ViewMode;
  activeFloor?: number | null;
  resetKey?: number;
  isLoading?: boolean;
  error?: string | null;
}

function addOutlineEdges(group: THREE.Group, mesh: THREE.Mesh, outlineColor = 0x38bdf8, opacity = 1.0) {
  const edgesGeometry = new THREE.EdgesGeometry(mesh.geometry);
  const edgesMaterial = new THREE.LineBasicMaterial({
    color: outlineColor,
    linewidth: 1,
    transparent: opacity < 1,
    opacity,
  });
  const edges = new THREE.LineSegments(edgesGeometry, edgesMaterial);
  edges.position.copy(mesh.position);
  edges.rotation.copy(mesh.rotation);
  edges.scale.copy(mesh.scale);
  group.add(edges);
}

function getComponentMaterial(comp: GeometryComponent, viewMode: ViewMode = "exterior"): THREE.Material {
  const { type, name, material_color } = comp;
  const lowerName = name.toLowerCase();
  const lowerType = type.toLowerCase();

  // 1. Site boundary
  if (lowerType === "site_plot" || lowerName.includes("site")) {
    return new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.9, metalness: 0.1 });
  }

  // 2. Floor slabs
  if (lowerType === "floor_slab" || lowerName.includes("slab")) {
    return new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.5, metalness: 0.2 });
  }

  // 3. Structural columns
  if (lowerType === "column" || lowerName.includes("column")) {
    return new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.4, metalness: 0.3 });
  }

  // 4. Exterior wall envelope
  if (lowerType === "wall_volume" || lowerType === "wall_exterior") {
    if (viewMode === "interior" || viewMode === "floor_plan") {
      // Hide exterior walls or make nearly invisible to expose the rooms
      return new THREE.MeshPhysicalMaterial({
        color: 0xf8fafc,
        transparent: true,
        opacity: 0.05,
        roughness: 0.1,
      });
    }
    if (viewMode === "cutaway") {
      return new THREE.MeshPhysicalMaterial({
        color: 0x94a3b8,
        transparent: true,
        opacity: 0.18,
        roughness: 0.2,
        metalness: 0.1,
      });
    }
    return new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.5, metalness: 0.1 });
  }

  // 5. Interior partition walls
  if (lowerType === "interior_wall" || lowerName.includes("wall_center") || lowerName.includes("wall_transverse")) {
    return new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.4, metalness: 0.1 });
  }

  // 6. Windows & Glass
  if (lowerType === "window" || lowerName.includes("window")) {
    return new THREE.MeshPhysicalMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: viewMode === "interior" ? 0.3 : 0.65,
      roughness: 0.1,
      metalness: 0.1,
      transmission: 0.7,
    });
  }

  // 7. Balcony
  if (lowerType === "balcony" || lowerName.includes("balcony")) {
    return new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.4, metalness: 0.3 });
  }

  // 8. Doors
  if (lowerType === "door" || lowerName.includes("door")) {
    return new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.6, metalness: 0.2 });
  }

  // 9. Roof
  if (lowerType === "roof" || lowerType === "roof_pitched" || lowerName.includes("roof")) {
    if (viewMode === "interior" || viewMode === "cutaway" || viewMode === "floor_plan") {
      return new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.0 });
    }
    return new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5, metalness: 0.3 });
  }

  // 10. Furniture items
  if (lowerType === "furniture_sofa" || lowerName.includes("sofa")) {
    return new THREE.MeshStandardMaterial({ color: 0x1e3a8a, roughness: 0.8, metalness: 0.1 });
  }
  if (lowerType === "furniture_bed" || lowerName.includes("bed") || lowerName.includes("headboard")) {
    return new THREE.MeshStandardMaterial({ color: 0xb45309, roughness: 0.6, metalness: 0.2 });
  }
  if (lowerType === "furniture_table" || lowerName.includes("table") || lowerName.includes("desk")) {
    return new THREE.MeshStandardMaterial({ color: 0x78350f, roughness: 0.5, metalness: 0.2 });
  }
  if (lowerType === "furniture_chair" || lowerName.includes("chair")) {
    return new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.6, metalness: 0.2 });
  }
  if (lowerType === "furniture_counter" || lowerName.includes("counter")) {
    return new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.3, metalness: 0.4 });
  }
  if (lowerType === "furniture_wardrobe" || lowerName.includes("wardrobe") || lowerName.includes("bookshelf")) {
    return new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5, metalness: 0.2 });
  }
  if (lowerType === "furniture_tv_unit" || lowerName.includes("tv")) {
    return new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.2, metalness: 0.6 });
  }
  if (lowerType === "furniture_sanitary" || lowerName.includes("toilet") || lowerName.includes("basin")) {
    return new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.1, metalness: 0.1 });
  }
  if (lowerType === "staircase" || lowerName.includes("stair")) {
    return new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.5, metalness: 0.4 });
  }

  // 11. Bridge Structural Components
  if (lowerType === "arch_rib" || lowerName.includes("arch_rib")) {
    return new THREE.MeshStandardMaterial({ color: 0xf59e0b, roughness: 0.3, metalness: 0.7 });
  }
  if (lowerType === "main_cable" || lowerType === "stay_cable" || lowerName.includes("cable")) {
    return new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.2, metalness: 0.8 });
  }
  if (lowerType === "hanger" || lowerName.includes("hanger")) {
    return new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.2, metalness: 0.9 });
  }
  if (lowerType === "tower" || lowerName.includes("tower") || lowerName.includes("pylon")) {
    return new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.5, metalness: 0.4 });
  }
  if (lowerType.includes("truss") || lowerName.includes("truss") || lowerName.includes("chord")) {
    return new THREE.MeshStandardMaterial({ color: 0x38bdf8, roughness: 0.3, metalness: 0.7 });
  }
  if (lowerType === "deck" || lowerName.includes("deck")) {
    return new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.6, metalness: 0.2 });
  }
  if (lowerType === "girder" || lowerName.includes("girder")) {
    return new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.4, metalness: 0.6 });
  }
  if (lowerType === "abutment" || lowerType === "pier" || lowerType === "anchorage" || lowerName.includes("support")) {
    return new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.7, metalness: 0.2 });
  }

  if (material_color) {
    return new THREE.MeshStandardMaterial({ color: new THREE.Color(material_color), roughness: 0.5 });
  }

  return new THREE.MeshStandardMaterial({ color: 0x0ea5e9, roughness: 0.4, metalness: 0.3 });
}

function buildFromParametricGeometry(
  paramGeo: ParametricGeometry,
  viewMode: ViewMode = "exterior",
  activeFloor: number | null = null
): THREE.Group {
  const group = new THREE.Group();

  for (const comp of paramGeo.components) {
    // Floor filtering
    if (activeFloor !== null && activeFloor !== undefined && comp.floor_number !== undefined && comp.floor_number !== null) {
      if (comp.floor_number !== activeFloor && comp.type !== "site_plot") {
        continue;
      }
    }

    // View mode roof filtering
    if (
      (viewMode === "interior" || viewMode === "cutaway" || viewMode === "floor_plan") &&
      (comp.type === "roof" || comp.type === "roof_pitched" || comp.name.includes("roof"))
    ) {
      continue;
    }

    // View mode exterior wall filtering in interior/floor_plan mode
    if ((viewMode === "interior" || viewMode === "floor_plan") && comp.type === "wall_volume") {
      continue;
    }

    const [dimX, dimY, dimZ] = comp.dimensions_m;
    const [posX, posY, posZ] = comp.position_m;

    let meshGeometry: THREE.BufferGeometry;
    if (comp.type === "cylinder" || comp.name.includes("cylinder")) {
      meshGeometry = new THREE.CylinderGeometry(dimX / 2, dimX / 2, dimY, 32);
    } else if (comp.type === "sphere" || comp.name.includes("sphere")) {
      meshGeometry = new THREE.SphereGeometry(dimX / 2, 32, 16);
    } else if (comp.type === "cone" || comp.name.includes("cone")) {
      meshGeometry = new THREE.ConeGeometry(dimX / 2, dimY, 32);
    } else {
      meshGeometry = new THREE.BoxGeometry(dimX, dimY, dimZ);
    }

    const material = getComponentMaterial(comp, viewMode);
    const mesh = new THREE.Mesh(meshGeometry, material);
    mesh.position.set(posX, posY, posZ);

    if (comp.rotation_rad) {
      const [rotX, rotY, rotZ] = comp.rotation_rad;
      mesh.rotation.set(rotX, rotY, rotZ);
    }

    mesh.castShadow = true;
    mesh.receiveShadow = true;
    group.add(mesh);

    // Outline edges
    let outlineColor = 0x0284c7;
    if (comp.type === "site_plot") outlineColor = 0x64748b;
    if (comp.type.startsWith("furniture_")) outlineColor = 0xf59e0b;
    if (comp.type === "interior_wall") outlineColor = 0x94a3b8;
    if (comp.type === "staircase") outlineColor = 0x38bdf8;

    const opacity = viewMode === "cutaway" && comp.type === "wall_volume" ? 0.25 : 0.9;
    addOutlineEdges(group, mesh, outlineColor, opacity);
  }

  return group;
}

function buildFallbackPrimitive(design: DesignSpec): THREE.Group {
  const group = new THREE.Group();
  const { length, width, height } = design.dimensions_mm;
  const lenM = length / 1000;
  const widM = width / 1000;
  const heiM = height / 1000;

  const round = ["shaft", "cylinder", "hole"].includes(design.object_type);
  let geometry: THREE.BufferGeometry;

  if (round) {
    geometry = new THREE.CylinderGeometry(widM / 2, widM / 2, lenM, 64);
  } else if (design.object_type === "sphere") {
    geometry = new THREE.SphereGeometry(widM / 2, 48, 32);
  } else if (design.object_type === "cone") {
    geometry = new THREE.ConeGeometry(widM / 2, lenM, 64);
  } else {
    geometry = new THREE.BoxGeometry(lenM, heiM, widM);
  }

  const material =
    design.material === "steel"
      ? new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.75, roughness: 0.25 })
      : new THREE.MeshStandardMaterial({ color: 0x38bdf8, roughness: 0.4, metalness: 0.2 });

  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.y = round || design.object_type === "cone" ? lenM / 2 : heiM / 2;
  mesh.castShadow = true;
  mesh.receiveShadow = true;

  group.add(mesh);
  addOutlineEdges(group, mesh, 0x0284c7);
  return group;
}

function fitCameraToObject(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  object: THREE.Object3D,
  viewMode: ViewMode = "exterior"
) {
  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) return;

  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());

  const maxSize = Math.max(size.x, size.y, size.z, 0.5);
  const fov = camera.fov * (Math.PI / 180);
  let distance = Math.abs(maxSize / Math.sin(fov / 2)) * 1.15;
  distance = Math.max(distance, 2.0);

  camera.near = Math.max(0.01, distance / 100);
  camera.far = Math.max(2000, distance * 100);

  if (viewMode === "floor_plan") {
    // Top-down overhead camera
    camera.position.set(center.x, center.y + distance * 1.3, center.z + 0.01);
  } else if (viewMode === "interior") {
    // Eye-level closer interior inspection
    camera.position.set(center.x + distance * 0.45, center.y + distance * 0.3, center.z + distance * 0.7);
  } else if (viewMode === "cutaway") {
    // Isometric section view
    camera.position.set(center.x + distance * 0.75, center.y + distance * 0.45, center.z + distance * 0.85);
  } else {
    // Exterior default 45 degree angle
    camera.position.set(center.x + distance * 0.85, center.y + distance * 0.55, center.z + distance * 0.85);
  }

  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();

  debugLog("Camera Positioned", { viewMode, center: center.toArray(), size: size.toArray(), distance });
}

export function ModelViewport({
  design,
  geometry,
  showGrid = true,
  showAxes = true,
  theme = "dark",
  viewMode = "exterior",
  activeFloor = null,
  resetKey = 0,
  isLoading = false,
  error = null,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    setRenderError(null);
    debugLog("Initializing Three.js Scene", { theme, showGrid, showAxes, viewMode, activeFloor });

    const isDark = theme === "dark";
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(isDark ? "#0b0f19" : "#f8fafc");

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 50000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";

    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;

    // 1. Ambient & Sky/Ground Light
    const ambientLight = new THREE.AmbientLight(0xffffff, isDark ? 1.5 : 1.2);
    scene.add(ambientLight);

    const hemiLight = new THREE.HemisphereLight(0xffffff, isDark ? 0x1e293b : 0x94a3b8, isDark ? 1.8 : 1.5);
    scene.add(hemiLight);

    // 2. Key & Fill Directional Lights
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.5);
    keyLight.position.set(25, 40, 25);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.width = 2048;
    keyLight.shadow.mapSize.height = 2048;
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x60a5fa, 1.2);
    fillLight.position.set(-25, 20, -25);
    scene.add(fillLight);

    // 3. Interior Point Lights for room illumination
    if (viewMode === "interior" || viewMode === "cutaway" || viewMode === "floor_plan") {
      const roomLight1 = new THREE.PointLight(0xffedd5, 1.8, 30);
      roomLight1.position.set(0, 4, 0);
      scene.add(roomLight1);

      const roomLight2 = new THREE.PointLight(0xe0f2fe, 1.5, 30);
      roomLight2.position.set(0, 8, 0);
      scene.add(roomLight2);
    }

    // 4. Grid & Axes Helpers
    const gridColor1 = isDark ? 0x475569 : 0xcbcee0;
    const gridColor2 = isDark ? 0x1e293b : 0xe2e8f0;
    const grid = new THREE.GridHelper(120, 48, gridColor1, gridColor2);
    grid.position.y = -0.01;
    grid.visible = showGrid;
    scene.add(grid);

    const axes = new THREE.AxesHelper(6);
    axes.visible = showAxes;
    scene.add(axes);

    let modelGroup: THREE.Group | null = null;

    try {
      if (geometry && geometry.components && geometry.components.length > 0) {
        modelGroup = buildFromParametricGeometry(geometry, viewMode, activeFloor);
      } else if (design) {
        modelGroup = buildFallbackPrimitive(design);
      }

      if (modelGroup && modelGroup.children.length > 0) {
        scene.add(modelGroup);
        fitCameraToObject(camera, controls, modelGroup, viewMode);
        debugLog("Model Rendered Successfully", {
          componentsCount: modelGroup.children.length,
          type: geometry?.type || design?.object_type,
          viewMode,
        });
      } else {
        camera.position.set(12, 10, 12);
        controls.target.set(0, 0, 0);
        controls.update();
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "3D Mesh rendering failed";
      setRenderError(errMsg);
      debugLog("Model Render Error", { error: errMsg });
    }

    const resize = () => {
      if (!container) return;
      const width = container.clientWidth || container.getBoundingClientRect().width;
      const height = container.clientHeight || container.getBoundingClientRect().height;
      if (!width || !height) return;

      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const observer = new ResizeObserver(() => {
      requestAnimationFrame(resize);
    });
    observer.observe(container);
    requestAnimationFrame(resize);

    let animationFrameId = 0;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      animationFrameId = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      cancelAnimationFrame(animationFrameId);
      observer.disconnect();
      controls.dispose();
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [design, geometry, showGrid, showAxes, theme, viewMode, activeFloor, resetKey]);

  return (
    <div className={`viewport-container ${theme}`} style={{ position: "relative", width: "100%", height: "100%", minHeight: 0 }}>
      <div className="viewport" ref={containerRef} aria-label="Interactive 3D model viewport" style={{ width: "100%", height: "100%" }} />

      {isLoading && (
        <div className="viewer-overlay loading">
          <div className="spinner" />
          <span>Generating CAD geometry…</span>
        </div>
      )}

      {(error || renderError) && (
        <div className="viewer-overlay error">
          <span className="error-icon">⚠️</span>
          <strong>3D Model Generation Error</strong>
          <p>{error || renderError}</p>
        </div>
      )}

      {!design && !geometry && !isLoading && !error && (
        <div className="viewer-empty">
          <span className="empty-logo">◈</span>
          <strong>Your 3D model will appear here</strong>
          <p>Enter a prompt in the chat (e.g. "a house for 30×40 site with 2 story") to generate a preliminary model.</p>
        </div>
      )}
    </div>
  );
}
