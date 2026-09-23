import * as THREE from "three";
import { OBJExporter } from "three/examples/jsm/exporters/OBJExporter.js";
import type { ParametricGeometry, DesignSpec } from "../types";

export function exportGeometryToOBJ(
  geometry: ParametricGeometry | null,
  design: DesignSpec | null,
  filename = "cad_model.obj"
) {
  if (!geometry || !geometry.components || geometry.components.length === 0) {
    alert("No geometry components to export.");
    return;
  }

  const group = new THREE.Group();

  for (const comp of geometry.components) {
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

    const material = new THREE.MeshBasicMaterial({ color: 0xcccccc });
    const mesh = new THREE.Mesh(meshGeometry, material);
    mesh.name = `${comp.name}_${comp.type}`;
    mesh.position.set(posX, posY, posZ);

    if (comp.rotation_rad) {
      const [rx, ry, rz] = comp.rotation_rad;
      mesh.rotation.set(rx, ry, rz);
    }

    group.add(mesh);
  }

  const exporter = new OBJExporter();
  const objData = exporter.parse(group);

  const blob = new Blob([objData], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.endsWith(".obj") ? filename : `${filename}.obj`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
