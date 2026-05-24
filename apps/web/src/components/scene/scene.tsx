"use client";

import { useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
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

export function Scene({ bundle, layout }: SceneProps) {
  return (
    <Canvas
      gl={{
        antialias: true,
        powerPreference: "high-performance",
        toneMapping: THREE.NoToneMapping, // we use the post-fx pass instead
        outputColorSpace: THREE.SRGBColorSpace,
        // Prefer a stencil buffer disabled — we don't use it and it costs
        // memory on high-DPI displays.
        stencil: false,
        depth: true,
      }}
      camera={{
        position: [0, 60, 320],
        near: 0.1,
        far: 5000,
        fov: 50,
      }}
      // Tell R3F to clear to pure black.
      onCreated={({ gl }) => {
        gl.setClearColor(0x000000, 1);
      }}
      // Cap DPR at 2 — diminishing returns above 2 and big perf cost on 3x
      // Retina displays. Floor at 1.5 so we never look pixelated.
      dpr={[1.5, 2]}
      className="absolute inset-0"
    >
      {/* Subtle ambient + a single directional rim light. With the body now
          using MeshStandardMaterial, a touch of directional light gives the
          spheres a proper round shading gradient instead of looking flat. */}
      <ambientLight intensity={0.18} />
      <directionalLight position={[200, 300, 200]} intensity={0.5} />

      <fog attach="fog" args={["#020818", 600, 1800]} />

      <Starfield count={1800} />

      {bundle && layout && (
        <SceneContent bundle={bundle} layout={layout} />
      )}

      <CameraRig hasContent={!!bundle} layout={layout} />

      {/*
        Post-processing pipeline:
          - Bloom is tuned for *tight* glow rather than a soft haze. Higher
            threshold + smaller radius keeps the highlight close to the orb,
            which makes the orbs themselves read as crisp circles.
          - ACES filmic tone mapping for cinematic colors.
       */}
      <EffectComposer multisampling={4}>
        <Bloom
          intensity={0.95}
          luminanceThreshold={0.55}
          luminanceSmoothing={0.20}
          mipmapBlur
          radius={0.45}
        />
        <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
      </EffectComposer>
    </Canvas>
  );
}

// ---------------------------------------------------------------------------
// Content — orbs + edges. Mounted only when we have data.
// ---------------------------------------------------------------------------

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

  const nodeById = useMemo(
    () => new Map(bundle.nodes.map((n) => [n.id, n])),
    [bundle],
  );

  return (
    <group>
      {/* Connections rendered first so orbs draw on top of them. */}
      {bundle.edges.map((e) => {
        const src = layout.positions.get(e.source);
        const tgt = layout.positions.get(e.target);
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
        const pos = layout.positions.get(node.id);
        if (!pos) return null;
        return (
          <Orb
            key={node.id}
            node={node}
            position={pos}
            selected={selectedNodeId === node.id}
            zoomLevel={zoomLevel}
            onClick={(id) => {
              setSelectedNodeId(id === selectedNodeId ? null : id);
            }}
          />
        );
      })}
    </group>
  );
}

// ---------------------------------------------------------------------------
// CameraRig — damped orbit + auto-frame on first content + reset/frame
// commands triggered from the HUD.
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

  // Helper: compute a flattering camera frame for the whole layout.
  const computeFitFrame = () => {
    if (!layout || layout.nodes.length === 0) return null;
    const box = new THREE.Box3();
    for (const n of layout.nodes) {
      box.expandByPoint(new THREE.Vector3(n.x, n.y, n.z));
    }
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z, 80);
    // Pull the camera back proportional to the largest dimension.
    const distance = maxDim * 1.6 + 80;
    const pos = new THREE.Vector3(
      center.x + distance * 0.3,
      center.y + distance * 0.4,
      center.z + distance,
    );
    return { pos, look: center };
  };

  // First frame on layout load.
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

  // Reset camera command from the HUD.
  useEffect(() => {
    if (cameraResetTick === 0) return;
    const frame = computeFitFrame();
    if (frame) {
      targetPosRef.current = frame.pos;
      targetLookRef.current = frame.look;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraResetTick]);

  // Frame the selected node — fly camera so it's centered + close.
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

  // Smoothly lerp the camera + orbit target toward whatever was requested.
  useFrame((_, delta) => {
    if (!controlsRef.current) return;
    if (targetPosRef.current) {
      const t = 1 - Math.exp(-delta * 3);
      camera.position.lerp(targetPosRef.current, t);
      // Snap-stop once close enough.
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
