"use client";

import { useEffect, useMemo, useRef } from "react";
import { Canvas, useThree } from "@react-three/fiber";
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

      <CameraRig hasContent={!!bundle} />

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
// CameraRig — damped orbit + auto-frame on first content.
// ---------------------------------------------------------------------------

function CameraRig({ hasContent }: { hasContent: boolean }) {
  const { camera } = useThree();
  const controlsRef = useRef<any>(null);
  const framedOnceRef = useRef(false);

  // When content arrives the first time, gently dolly to a flattering position.
  useEffect(() => {
    if (!hasContent || framedOnceRef.current) return;
    framedOnceRef.current = true;
    // Reset camera to a stable starting frame; OrbitControls.update() will
    // pick up the new target.
    camera.position.set(0, 80, 360);
    camera.lookAt(0, 0, 0);
    controlsRef.current?.update();
  }, [hasContent, camera]);

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      // Damping = the secret sauce of "smooth as hell".
      enableDamping
      dampingFactor={0.07}
      rotateSpeed={0.6}
      panSpeed={0.6}
      zoomSpeed={0.8}
      minDistance={20}
      maxDistance={2000}
      // Don't constrain vertical rotation — let the user fly anywhere.
      minPolarAngle={0}
      maxPolarAngle={Math.PI}
      // Right-click to pan, left to rotate, scroll to zoom.
      mouseButtons={{
        LEFT: 0, // ROTATE
        MIDDLE: 1, // DOLLY (zoom)
        RIGHT: 2, // PAN
      }}
    />
  );
}
