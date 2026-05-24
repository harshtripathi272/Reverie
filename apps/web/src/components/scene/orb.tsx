"use client";

import { useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Sphere } from "@react-three/drei";

import { OrbLabel } from "@/components/scene/orb-label";
import { radiusFromSalience, visualFor } from "@/lib/colors";
import type { GraphNode, ZoomLevel } from "@/lib/types";

/**
 * One glowing orb.
 *
 * Visual structure (kept deliberately simple to avoid the "fuzz pile-up" of
 * stacking many transparent layers):
 *
 *   1. Body — fully opaque, high-segment-count sphere. This gives the orb a
 *      clean, crisp silhouette regardless of how aggressive the bloom is.
 *      The body's emissive material drives the bloom highlights.
 *
 *   2. Halo — a slightly larger sphere (×1.18) with a Fresnel rim shader.
 *      Only the silhouette rim is visible.
 *
 *   3. Selection ring — torus, only when ``selected``.
 *
 *   4. Label — DOM <Html> floating above the orb when visibility rules say so.
 */

interface OrbProps {
  node: GraphNode;
  position: THREE.Vector3;
  selected?: boolean;
  zoomLevel: ZoomLevel;
  onClick?: (id: string) => void;
}

const HALO_VERTEX_SHADER = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vViewDir;

  void main() {
    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
    vec4 viewPosition = viewMatrix * worldPosition;
    vNormal = normalize(mat3(modelMatrix) * normal);
    vViewDir = normalize(cameraPosition - worldPosition.xyz);
    gl_Position = projectionMatrix * viewPosition;
  }
`;

const HALO_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform float uIntensity;
  uniform float uTime;
  uniform float uPulse;

  varying vec3 vNormal;
  varying vec3 vViewDir;

  void main() {
    float fresnel = 1.0 - max(dot(vNormal, vViewDir), 0.0);
    float rim = pow(fresnel, 4.0);
    float pulse = 1.0 + uPulse * 0.30 * sin(uTime * 2.4);
    float alpha = rim * uIntensity * pulse;
    vec3 col = uColor * (0.9 + rim * 1.6);
    gl_FragColor = vec4(col, alpha);
  }
`;

export function Orb({
  node,
  position,
  selected = false,
  zoomLevel,
  onClick,
}: OrbProps) {
  const visual = visualFor(node.type);
  const baseRadius = visual.radius;
  const radius = radiusFromSalience(baseRadius, node.salience);
  const [hovered, setHovered] = useState(false);

  // Pulse strength: failed orbs breathe most, then critical-path, then anomalies.
  const pulse = useMemo(() => {
    if (node.type.endsWith(".failed")) return 1.0;
    if (node.onCriticalPath) return 0.6;
    if (node.anomalies.length > 0) return 0.4;
    return 0.0;
  }, [node.type, node.onCriticalPath, node.anomalies.length]);

  // Halo shader uniforms.
  const haloUniforms = useMemo(
    () => ({
      uColor: { value: visual.color.clone() },
      uIntensity: { value: visual.glow * (selected ? 1.55 : 1.0) },
      uTime: { value: 0 },
      uPulse: { value: pulse },
    }),
    [visual.color, visual.glow, selected, pulse],
  );

  const haloMaterial = useMemo(
    () =>
      new THREE.ShaderMaterial({
        uniforms: haloUniforms,
        vertexShader: HALO_VERTEX_SHADER,
        fragmentShader: HALO_FRAGMENT_SHADER,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.FrontSide,
        toneMapped: false,
      }),
    [haloUniforms],
  );

  const bodyMaterial = useMemo(() => {
    const baseColor = visual.color;
    return new THREE.MeshStandardMaterial({
      color: baseColor,
      emissive: baseColor,
      emissiveIntensity: visual.glow * 1.4,
      roughness: 0.42,
      metalness: 0.0,
      transparent: false,
      toneMapped: false,
    });
  }, [visual.color, visual.glow]);

  // Animate selection / hover scale + halo pulse.
  const groupRef = useRef<THREE.Group>(null);
  const targetScale = selected ? 1.16 : hovered ? 1.08 : 1.0;
  useFrame((state, delta) => {
    if (!groupRef.current) return;
    const cur = groupRef.current.scale.x;
    const next = THREE.MathUtils.lerp(cur, targetScale, 1 - Math.exp(-delta * 8));
    groupRef.current.scale.setScalar(next);
    haloUniforms.uTime.value = state.clock.elapsedTime;
  });

  // Geometry resolution.
  const segments = baseRadius >= 7 ? 64 : baseRadius >= 5 ? 48 : 36;

  // Label visibility rules — see ``OrbLabel`` and the explorer header.
  // Goals + subagents + failures are always labelled; everything else only
  // when hovered/selected at L3+.
  const labelVisible = computeLabelVisibility({
    node,
    zoomLevel,
    hovered,
    selected,
  });

  // Lift the label slightly above the orb so the halo doesn't push through it.
  const labelOffset = radius * 1.7;

  return (
    <group
      ref={groupRef}
      position={position}
      onPointerDown={(e) => {
        e.stopPropagation();
        onClick?.(node.id);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = "";
      }}
    >
      {/* Halo first — renderOrder lower so the body draws on top. */}
      <Sphere
        args={[radius * 1.18, segments, segments]}
        material={haloMaterial}
        renderOrder={0}
      />

      {/* Body. */}
      <Sphere
        args={[radius, segments, segments]}
        material={bodyMaterial}
        renderOrder={1}
      />

      {/* Selection ring. */}
      {selected && (
        <mesh rotation={[Math.PI / 2, 0, 0]} renderOrder={2}>
          <torusGeometry args={[radius * 1.85, 0.15, 16, 96]} />
          <meshBasicMaterial
            color={visual.hex}
            transparent
            opacity={0.95}
            toneMapped={false}
          />
        </mesh>
      )}

      <OrbLabel
        node={node}
        offset={labelOffset}
        visible={labelVisible}
        emphasised={hovered || selected}
      />
    </group>
  );
}

// ---------------------------------------------------------------------------
// Label visibility — encodes the SRS-style "show fewer labels at higher
// detail" rule.
// ---------------------------------------------------------------------------

function computeLabelVisibility({
  node,
  zoomLevel,
  hovered,
  selected,
}: {
  node: GraphNode;
  zoomLevel: ZoomLevel;
  hovered: boolean;
  selected: boolean;
}): boolean {
  if (hovered || selected) return true;
  // L1 / L2 — few orbs, label them all.
  if (zoomLevel <= 2) return true;
  // L3 — only label "anchor" nodes. Tools/memory/etc. are too dense.
  if (zoomLevel === 3) {
    if (node.type.startsWith("goal.")) return true;
    if (node.type.startsWith("subagent.")) return true;
    if (node.type.endsWith(".failed")) return true;
    if (node.onCriticalPath) return true;
    return false;
  }
  // L4 — raw view; only label on hover/selection (already returned above).
  return false;
}
