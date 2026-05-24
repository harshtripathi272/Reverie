"use client";

import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Sphere } from "@react-three/drei";

import { radiusFromSalience, visualFor } from "@/lib/colors";
import type { GraphNode } from "@/lib/types";

/**
 * One glowing orb. Custom shader gives a soft Fresnel rim — looks like a
 * bioluminescent organism rather than a flat sphere with bloom dialed up.
 *
 * Three layers stack (cheaply) per orb:
 *
 *   1. Inner core: small, ultra-bright, contributes most of the bloom
 *   2. Mantle: emissive sphere at the visible radius
 *   3. Halo: a slightly larger transparent sphere with rim-only opacity
 *      so the silhouette glows even at oblique camera angles
 *
 * Failed orbs and on-critical-path orbs pulse via uniform time.
 */

interface OrbProps {
  node: GraphNode;
  position: THREE.Vector3;
  selected?: boolean;
  onClick?: (id: string) => void;
}

const HALO_VERTEX_SHADER = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vViewPosition;
  void main() {
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vViewPosition = -mvPosition.xyz;
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const HALO_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform float uIntensity;
  uniform float uTime;
  uniform float uPulse;

  varying vec3 vNormal;
  varying vec3 vViewPosition;

  void main() {
    vec3 viewDir = normalize(vViewPosition);
    // Fresnel: brightest where the normal is perpendicular to the view.
    float fresnel = 1.0 - max(dot(vNormal, viewDir), 0.0);
    fresnel = pow(fresnel, 2.5);

    // Pulse modulates the rim — slow breath when uPulse > 0.
    float pulse = 1.0 + uPulse * 0.4 * sin(uTime * 2.5);

    float alpha = fresnel * uIntensity * pulse;
    vec3 col = uColor * (0.6 + fresnel * 1.8);
    gl_FragColor = vec4(col, alpha);
  }
`;

export function Orb({ node, position, selected = false, onClick }: OrbProps) {
  const visual = visualFor(node.type);
  const baseRadius = visual.radius;
  const radius = radiusFromSalience(baseRadius, node.salience);

  // Pulse strength: 1.0 for failed events / on-critical-path, 0.5 for
  // anomalies, 0.0 otherwise.
  const pulse = useMemo(() => {
    if (node.type.endsWith(".failed")) return 1.0;
    if (node.onCriticalPath) return 0.7;
    if (node.anomalies.length > 0) return 0.5;
    return 0.0;
  }, [node.type, node.onCriticalPath, node.anomalies.length]);

  // Halo material with custom shader — enabled by uniforms we can update.
  const haloUniforms = useMemo(
    () => ({
      uColor: { value: visual.color.clone() },
      uIntensity: { value: visual.glow * (selected ? 1.6 : 1.0) },
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
      }),
    [haloUniforms],
  );

  // Core / mantle materials — fully emissive (post-processing bloom does the
  // glow propagation; these stay matte-bright).
  const coreMaterial = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: visual.color.clone().multiplyScalar(2.4),
        transparent: true,
        opacity: 0.95,
        toneMapped: false,
      }),
    [visual.color],
  );

  const mantleMaterial = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: visual.color,
        emissive: visual.color,
        emissiveIntensity: visual.glow * 1.6,
        roughness: 0.3,
        metalness: 0.0,
        transparent: true,
        opacity: 0.9,
        toneMapped: false,
      }),
    [visual.color, visual.glow],
  );

  // Animate selection scale + halo pulse.
  const groupRef = useRef<THREE.Group>(null);
  const targetScale = selected ? 1.18 : 1.0;
  useFrame((state, delta) => {
    if (!groupRef.current) return;
    // Smooth scale lerp toward target — never snap.
    const cur = groupRef.current.scale.x;
    const next = THREE.MathUtils.lerp(cur, targetScale, 1 - Math.exp(-delta * 8));
    groupRef.current.scale.setScalar(next);
    // Drive halo pulse uniform.
    haloUniforms.uTime.value = state.clock.elapsedTime;
  });

  // Cap segment count by orb size for perf — small orbs don't need 32 segments.
  const segments = baseRadius >= 6 ? 24 : baseRadius >= 4 ? 16 : 12;

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
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        document.body.style.cursor = "";
      }}
    >
      {/* Halo (transparent, fresnel rim). */}
      <Sphere
        args={[radius * 1.65, segments, segments]}
        material={haloMaterial}
      />
      {/* Mantle (visible body). */}
      <Sphere
        args={[radius, segments, segments]}
        material={mantleMaterial}
      />
      {/* Bright core. */}
      <Sphere
        args={[radius * 0.55, segments, segments]}
        material={coreMaterial}
      />
      {/* Selection ring — only shown when selected. */}
      {selected && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[radius * 2.1, 0.25, 12, 64]} />
          <meshBasicMaterial
            color={visual.hex}
            transparent
            opacity={0.85}
            toneMapped={false}
          />
        </mesh>
      )}
    </group>
  );
}
