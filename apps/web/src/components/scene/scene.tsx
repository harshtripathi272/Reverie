"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import {
  Bloom,
  EffectComposer,
  ToneMapping,
} from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import * as THREE from "three";

import { Connection } from "@/components/scene/connection";
import { Orb } from "@/components/scene/orb";
import { Starfield } from "@/components/scene/starfield";
import { useExplorerStore } from "@/lib/store";
import type { LaidOutGraph } from "@/lib/layout";
import type { GraphBundle } from "@/lib/types";

interface SceneProps {
  bundle: GraphBundle | null;
  layout: LaidOutGraph | null;
}

/**
 * Module-level shared ref so `SceneContent` can disable OrbitControls
 * during a drag without prop-drilling through three layers. We use a ref
 * (not state) so toggling it doesn't trigger a re-render of the whole
 * tree mid-drag.
 */
const orbitEnabledRef: { current: boolean } = { current: true };

export function Scene({ bundle, layout }: SceneProps) {
  return (
    <Canvas
      gl={{
        antialias: true,
        powerPreference: "high-performance",
        toneMapping: THREE.NoToneMapping,
        outputColorSpace: THREE.SRGBColorSpace,
        stencil: false,
        depth: true,
      }}
      camera={{
        position: [0, 60, 320],
        near: 0.1,
        far: 5000,
        fov: 50,
      }}
      onCreated={({ gl }) => {
        gl.setClearColor(0x000000, 1);
      }}
      dpr={[1.5, 2]}
      className="absolute inset-0"
    >
      <ambientLight intensity={0.20} />
      <directionalLight position={[200, 300, 200]} intensity={0.55} />

      <fog attach="fog" args={["#020818", 600, 1800]} />

      <Starfield count={1800} />

      {bundle && layout && (
        <SceneContent bundle={bundle} layout={layout} />
      )}

      <CameraRig hasContent={!!bundle} layout={layout} />

      <EffectComposer multisampling={4}>
        <Bloom
          intensity={0.45}
          luminanceThreshold={0.85}
          luminanceSmoothing={0.15}
          mipmapBlur
          radius={0.35}
        />
        <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
      </EffectComposer>
    </Canvas>
  );
}

// ---------------------------------------------------------------------------
// Content — orbs + edges. Implements drag-to-move.
// ---------------------------------------------------------------------------

interface DragState {
  nodeId: string;
  // World-space plane the drag is happening on.
  plane: THREE.Plane;
  // Offset between pointer hit point and orb center on the drag plane —
  // so the orb doesn't snap to wherever the cursor lands first.
  offset: THREE.Vector3;
  // Distance the pointer has moved since pointer-down — used to distinguish
  // a click from a drag.
  travelled: number;
}

const CLICK_VS_DRAG_THRESHOLD = 4; // world units

function SceneContent({
  bundle,
  layout,
}: {
  bundle: GraphBundle;
  layout: LaidOutGraph;
}) {
  const selectedNodeId = useExplorerStore((s) => s.selectedNodeId);
  const setSelectedNodeId = useExplorerStore((s) => s.setSelectedNodeId);
  const zoomLevel = useExplorerStore((s) => s.zoomLevel);
  const { camera, gl } = useThree();

  // Local mutable position map. Seeded from the layout the first time we
  // see it; re-seeded only when the underlying layout reference changes
  // (i.e. a fresh graph fetch). Drag updates write here.
  const [positions, setPositions] = useState<Map<string, THREE.Vector3>>(
    () => clonePositionMap(layout.positions),
  );
  useEffect(() => {
    setPositions(clonePositionMap(layout.positions));
  }, [layout]);

  const dragRef = useRef<DragState | null>(null);

  const nodeById = useMemo(
    () => new Map(bundle.nodes.map((n) => [n.id, n])),
    [bundle],
  );

  // ---------------------------------------------------------------- drag

  const onPointerDownNode = (id: string, e: ThreeEvent<PointerEvent>) => {
    const orb = positions.get(id);
    if (!orb) return;

    // Build the drag plane: perpendicular to the camera, passing through
    // the orb. Pointer movement gets projected onto this plane so the orb
    // moves in the camera's "screen plane" no matter where the camera is.
    const cameraDir = new THREE.Vector3();
    camera.getWorldDirection(cameraDir);
    const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(
      cameraDir.negate(), // plane normal points toward camera
      orb.clone(),
    );

    // Where on that plane was the initial pointer? Used as our offset
    // anchor so the orb tracks the cursor's relative motion, not absolute.
    const hitPoint = e.point.clone();
    const offset = orb.clone().sub(hitPoint);

    dragRef.current = {
      nodeId: id,
      plane,
      offset,
      travelled: 0,
    };

    // Capture the pointer so we keep getting events when the cursor
    // leaves the orb during fast drags.
    (e.target as Element | null)?.setPointerCapture?.(e.pointerId);

    // Disable orbit controls while dragging — otherwise the camera would
    // pan/orbit at the same time.
    orbitEnabledRef.current = false;

    document.body.style.cursor = "grabbing";
  };

  // Global pointer-move listener attached to the canvas DOM element. Using
  // the canvas ensures we still get events when the pointer leaves the
  // orb during a drag.
  useEffect(() => {
    const canvas = gl.domElement;

    const onMove = (ev: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;

      // Convert pointer to NDC.
      const rect = canvas.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((ev.clientX - rect.left) / rect.width) * 2 - 1,
        -((ev.clientY - rect.top) / rect.height) * 2 + 1,
      );
      const ray = new THREE.Raycaster();
      ray.setFromCamera(ndc, camera);

      // Intersect the ray with the drag plane to get the new world-space
      // pointer position.
      const target = new THREE.Vector3();
      const hit = ray.ray.intersectPlane(drag.plane, target);
      if (!hit) return;

      const newPos = target.add(drag.offset);
      setPositions((prev) => {
        const next = new Map(prev);
        const old = next.get(drag.nodeId);
        if (old) {
          drag.travelled += old.distanceTo(newPos);
        }
        next.set(drag.nodeId, newPos);
        return next;
      });
    };

    const onUp = (ev: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;

      // If they barely moved, treat it as a click → toggle selection.
      if (drag.travelled < CLICK_VS_DRAG_THRESHOLD) {
        const id = drag.nodeId;
        // Use the latest store snapshot, not the captured value.
        const current = useExplorerStore.getState().selectedNodeId;
        useExplorerStore
          .getState()
          .setSelectedNodeId(current === id ? null : id);
      }

      dragRef.current = null;
      orbitEnabledRef.current = true;
      document.body.style.cursor = "";
      try {
        (ev.target as Element).releasePointerCapture?.(ev.pointerId);
      } catch {
        // Some browsers throw if no capture was held — safe to ignore.
      }
    };

    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onUp);
    return () => {
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointercancel", onUp);
    };
  }, [camera, gl, setSelectedNodeId]);

  // ---------------------------------------------------------------- render

  return (
    <group>
      {/* Connections rendered first so orbs draw on top of them. */}
      {bundle.edges.map((e) => {
        const src = positions.get(e.source);
        const tgt = positions.get(e.target);
        if (!src || !tgt) return null;
        const targetNode = nodeById.get(e.target);
        return (
          <Connection
            key={`${e.source}->${e.target}`}
            edge={e}
            source={src}
            target={tgt}
            targetNode={targetNode}
            showFlow={e.onCriticalPath}
          />
        );
      })}

      {bundle.nodes.map((node) => {
        const pos = positions.get(node.id);
        if (!pos) return null;
        return (
          <Orb
            key={node.id}
            node={node}
            position={pos}
            selected={selectedNodeId === node.id}
            zoomLevel={zoomLevel}
            onPointerDownNode={onPointerDownNode}
          />
        );
      })}
    </group>
  );
}

function clonePositionMap(
  src: Map<string, THREE.Vector3>,
): Map<string, THREE.Vector3> {
  const out = new Map<string, THREE.Vector3>();
  for (const [k, v] of src) out.set(k, v.clone());
  return out;
}

// ---------------------------------------------------------------------------
// CameraRig — damped orbit + auto-frame on first content + reset/frame
// commands triggered from the HUD. Enabled state honors the drag flag.
// ---------------------------------------------------------------------------

function CameraRig({
  hasContent,
  layout,
}: {
  hasContent: boolean;
  layout: LaidOutGraph | null;
}) {
  const { camera } = useThree();
  const controlsRef = useRef<any>(null);
  const framedOnceRef = useRef(false);
  const targetPosRef = useRef<THREE.Vector3 | null>(null);
  const targetLookRef = useRef<THREE.Vector3 | null>(null);

  const cameraResetTick = useExplorerStore((s) => s.cameraResetTick);
  const frameSelectedTick = useExplorerStore((s) => s.frameSelectedTick);
  const selectedNodeId = useExplorerStore((s) => s.selectedNodeId);

  const computeFitFrame = () => {
    if (!layout || layout.nodes.length === 0) return null;
    const box = new THREE.Box3();
    for (const n of layout.nodes) {
      box.expandByPoint(new THREE.Vector3(n.x, n.y, n.z));
    }
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z, 80);
    const distance = maxDim * 1.6 + 80;
    const pos = new THREE.Vector3(
      center.x + distance * 0.3,
      center.y + distance * 0.4,
      center.z + distance,
    );
    return { pos, look: center };
  };

  useEffect(() => {
    if (!hasContent || framedOnceRef.current) return;
    framedOnceRef.current = true;
    const frame = computeFitFrame();
    if (frame) {
      targetPosRef.current = frame.pos;
      targetLookRef.current = frame.look;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasContent, layout]);

  useEffect(() => {
    if (cameraResetTick === 0) return;
    const frame = computeFitFrame();
    if (frame) {
      targetPosRef.current = frame.pos;
      targetLookRef.current = frame.look;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraResetTick]);

  useEffect(() => {
    if (frameSelectedTick === 0 || !selectedNodeId || !layout) return;
    const node = layout.nodes.find((n) => n.id === selectedNodeId);
    if (!node) return;
    const center = new THREE.Vector3(node.x, node.y, node.z);
    const distance = 90;
    targetPosRef.current = new THREE.Vector3(
      center.x + distance * 0.4,
      center.y + distance * 0.5,
      center.z + distance,
    );
    targetLookRef.current = center;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frameSelectedTick]);

  useFrame((_, delta) => {
    if (!controlsRef.current) return;
    // Sync orbit-controls enabled state with the drag flag every frame.
    controlsRef.current.enabled = orbitEnabledRef.current;
    if (targetPosRef.current) {
      const t = 1 - Math.exp(-delta * 3);
      camera.position.lerp(targetPosRef.current, t);
      if (camera.position.distanceTo(targetPosRef.current) < 0.4) {
        camera.position.copy(targetPosRef.current);
        targetPosRef.current = null;
      }
    }
    if (targetLookRef.current) {
      const t = 1 - Math.exp(-delta * 3);
      const cur = controlsRef.current.target as THREE.Vector3;
      cur.lerp(targetLookRef.current, t);
      if (cur.distanceTo(targetLookRef.current) < 0.4) {
        cur.copy(targetLookRef.current);
        targetLookRef.current = null;
      }
      controlsRef.current.update();
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.07}
      rotateSpeed={0.6}
      panSpeed={0.6}
      zoomSpeed={0.8}
      minDistance={20}
      maxDistance={3000}
      minPolarAngle={0}
      maxPolarAngle={Math.PI}
      mouseButtons={{
        LEFT: 0,
        MIDDLE: 1,
        RIGHT: 2,
      }}
    />
  );
}
