"use client";

import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Sphere } from "@react-three/drei";

import { radiusFromSalience, visualFor } from "@/lib/colors";
import type { GraphNode } from "@/lib/types";

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
 *   2. Halo — a slightly larger sphere (×1.15) with a Fresnel rim shader.
 *      Only the silhouette rim is visible; the front-facing pixels are fully
 *      transparent. Renders behind the body via render order so the body's
 *      hard edge wins where the two overlap.
 *
 *   3. Selection ring — torus, only when ``selected``.
 *
 * Pulse uniforms drive subtle "breath" animations on failed / on-critical
 * orbs without ever touching position or scale.
 */

interface OrbProps {
  node: GraphNode;
  position: THREE.Vector3;
  selected?: boolean;
  onClick?: (id: string) => void;
}

const HALO_VERTEX_SHADER = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vViewDir;

  void main() {
    vec4 worldPosition = modelMatrix * vec4(position, 1.0);
    vec4 viewPosition = viewMatrix * worldPosition;
    // World-space normal is what we want for a stable Fresnel — model normals
    // would shift as the orb scales.
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
    // Fresnel: 0 at front-facing pixels, 1 at the silhouette.
    float fresnel = 1.0 - max(dot(vNormal, vViewDir), 0.0);
    // Tighten the rim so it's a sharp ring instead of a soft cloud.
    float rim = pow(fresnel, 4.0);

    // Slow pulse modulates only the rim brightness — never grows the orb.
    float pulse = 1.0 + uPulse * 0.30 * sin(uTime * 2.4);

    float alpha = rim * uIntensity * pulse;
    // Color stays close to the base — no over-saturation when the rim is hot.
    vec3 col = uColor * (0.9 + rim * 1.6);
    gl_FragColor = vec4(col, alpha);
  }
`;

export function Orb({ node, position, selected = false, onClick }: OrbProps) {
  const visual = visualFor(node.type);
  const baseRadius = visual.radius;
  const radius = radiusFromSalience(baseRadius, node.salience);

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
        // Halo must NOT write to depth, otherwise it occludes other orbs
        // through its transparent center.
        depthWrite: false,
        // Render the rim only — back faces are pointed away from camera and
        // would double the alpha at glancing angles.
        side: THREE.FrontSide,
        toneMapped: false,
      }),
    [haloUniforms],
  );

  // Body — fully opaque emissive sphere. Bloom handles the outward glow;
  // we keep the silhouette razor sharp.
  const bodyMaterial = useMemo(() => {
    const baseColor = visual.color;
    return new THREE.MeshStandardMaterial({
      color: baseColor,
      emissive: baseColor,
      // emissiveIntensity > 1 pushes the pixel above the bloom threshold,
      // which is what gives the orb its outward glow. Tuned to read clean
      // at the dimmer bloom settings the scene uses.
      emissiveIntensity: visual.glow * 1.4,
      roughness: 0.42,
      metalness: 0.0,
      transparent: false,
      toneMapped: false,
    });
  }, [visual.color, visual.glow]);

  // Animate selection scale + halo pulse — never touches position.
  const groupRef = useRef<THREE.Group>(null);
  const targetScale = selected ? 1.16 : 1.0;
  useFrame((state, delta) => {
    if (!groupRef.current) return;
    const cur = groupRef.current.scale.x;
    const next = THREE.MathUtils.lerp(cur, targetScale, 1 - Math.exp(-delta * 8));
    groupRef.current.scale.setScalar(next);
    haloUniforms.uTime.value = state.clock.elapsedTime;
  });

  // Geometry resolution. Bigger orbs = more segments. Floor at 32 so even
  // small orbs read as clean spheres rather than polyhedra.
  const segments = baseRadius >= 7 ? 64 : baseRadius >= 5 ? 48 : 36;

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
      {/* Halo first — renderOrder lower so the body draws on top. */}
      <Sphere
        args={[radius * 1.18, segments, segments]}
        material={haloMaterial}
        renderOrder={0}
      />

      {/* Body — opaque, sharp silhouette. */}
      <Sphere
        args={[radius, segments, segments]}
        material={bodyMaterial}
        renderOrder={1}
      />

      {/* Selection ring — only when selected. Toroidal halo, not transparent. */}
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
    </group>
  );
}
