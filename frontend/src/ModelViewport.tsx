import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { DesignSpec } from "./types";

interface Props {
  design: DesignSpec | null;
}

export function ModelViewport({ design }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#111827");
    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1_000);
    camera.position.set(5, 4, 6);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    scene.add(new THREE.HemisphereLight(0xffffff, 0x334155, 2.5));
    const keyLight = new THREE.DirectionalLight(0xffffff, 3);
    keyLight.position.set(5, 7, 5);
    scene.add(keyLight);

    const grid = new THREE.GridHelper(10, 20, 0x64748b, 0x334155);
    scene.add(grid);
    const axes = new THREE.AxesHelper(1.25);
    scene.add(axes);

    if (design) {
      const { length, width, height } = design.dimensions_mm;
      const largest = Math.max(length, width, height);
      const scale = 3 / largest;
      const geometry = new THREE.BoxGeometry(length * scale, height * scale, width * scale);
      const material = new THREE.MeshStandardMaterial({ color: 0x38bdf8, metalness: 0.2, roughness: 0.42 });
      const box = new THREE.Mesh(geometry, material);
      box.position.y = (height * scale) / 2;
      scene.add(box);

      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({ color: 0xe0f2fe }),
      );
      edges.position.copy(box.position);
      scene.add(edges);
    }

    const resize = () => {
      const { width, height } = container.getBoundingClientRect();
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    let animationFrame: number;
    const animate = () => {
      controls.update();
      renderer.render(scene, camera);
      animationFrame = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      cancelAnimationFrame(animationFrame);
      observer.disconnect();
      controls.dispose();
      renderer.dispose();
      container.removeChild(renderer.domElement);
    };
  }, [design]);

  return <div className="viewport" ref={containerRef} aria-label="Interactive 3D model viewport" />;
}

