"use client";

import { useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Sphere } from "@react-three/drei";

import { OrbLabel } from "@/components/scene/orb-label";
import { radiusFromSalience, visualFor } from "@/lib/colors";
import { useExplorerStore } from "@/lib/store";
import type { GraphNode, ZoomLevel } from "@/lib/types";

/**
 * One glowing orb.
 *
 * Visual structure
 * ----------------
 *
 *   1. **Body** — fully opaque sphere. Crisp silhouette regardless of bloom.
 *      Carries a low emissive so the orb has presence without smearing.
 *
 *   2. **Halo** — slightly larger sphere with a Fresnel-rim shader, kept
 *      *subtle by default*. When the orb is hovered or selected, the halo
 *      brightens substantially — that's the "active highlight" cue.
 *
 *   3. **Selection ring** — torus, only when ``selected``. Hard, opaque,
 *      tells you *this is the one I clicked* at a glance.
 *
 *   4. **Hover ring** — softer torus on hover. Gives an affordance before
 *      the user commits to clicking.
 *
 *   5. **Label** — DOM <Html> floating above; visibility computed by zoom
 *      level + interaction state.
 *
 * Drag-to-move
 * ------------
 *
 * The Orb itself is just visuals. Pointer events bubble up to a dedicated
 * <DraggableOrbs> wrapper in scene.tsx that tracks pointer-down → drag →
 * pointer-up and writes the new position back to the layout map. This
 * separation keeps the visual code stateless about input mode.
 */

interface OrbProps {
  node: GraphNode;
  position: THREE.Vector3;
  selected?: boolean;
  inMultiSelection?: boolean;
  zoomLevel: ZoomLevel;
  onPointerDownNode?: (id: string, event: any) => void;
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
    // Sharper rim, narrower band — keeps the halo *suggestive* not loud.
    float rim = pow(fresnel, 5.0);
    float pulse = 1.0 + uPulse * 0.30 * sin(uTime * 2.4);
    float alpha = rim * uIntensity * pulse;
    // Don't push the rim color past the source color — that's what created
    // the over-saturated bloom in earlier versions.
    vec3 col = uColor * (0.7 + rim * 0.6);
    gl_FragColor = vec4(col, alpha);
  }
`;

export function Orb({
  node,
  position,
  selected = false,
  inMultiSelection = false,
  zoomLevel,
  onPointerDownNode,
}: OrbProps) {
  const visual = visualFor(node.type);
  const baseRadius = visual.radius;
  const radius = radiusFromSalience(baseRadius, node.salience);
  const [hovered, setHovered] = useState(false);

  // What annotations does this node have? Only the highest-priority one
  // shapes the visual treatment (avoid > focus > done > note).
  const annotations = useExplorerStore(
    (s) => s.annotationsByNode.get(node.id) ?? null,
  );
  const dominantAnnotation = useMemo(() => {
    if (!annotations || annotations.length === 0) return null;
    const order = ["avoid", "focus", "done", "note"] as const;
    for (const k of order) {
      const a = annotations.find((x) => x.kind === k);
      if (a) return a;
    }
    return annotations[0];
  }, [annotations]);

  // Pulse strength: failed orbs breathe most, then critical-path, then anomalies.
  const pulse = useMemo(() => {
    if (node.type.endsWith(".failed")) return 1.0;
    if (node.onCriticalPath) return 0.55;
    if (node.anomalies.length > 0) return 0.35;
    return 0.0;
  }, [node.type, node.onCriticalPath, node.anomalies.length]);

  // Active highlight: hover OR selection brightens the halo.
  // Base intensity is intentionally LOW (0.4×) so default scenes look
  // polished and quiet. Active state pops to ~1.5× — enough to draw the
  // eye without blowing the bloom out.
  const active = hovered || selected;
  const haloIntensity = visual.glow * (selected ? 1.5 : hovered ? 1.0 : 0.4);

  // Halo shader uniforms.
  const haloUniforms = useMemo(
    () => ({
      uColor: { value: visual.color.clone() },
      uIntensity: { value: haloIntensity },
      uTime: { value: 0 },
      uPulse: { value: pulse },
    }),
    // ``haloIntensity`` is intentionally NOT in deps — we mutate the
    // uniform directly in useFrame for smooth lerping.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visual.color, pulse],
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

  // Body — opaque, low emissive. Bloom handles outward propagation.
  const bodyMaterial = useMemo(() => {
    const baseColor = visual.color;
    // ``avoid`` annotation dims the body so it visually recedes — the user
    // told us this branch is a dead end, so we don't want it competing for
    // attention with active orbs.
    const dim = dominantAnnotation?.kind === "avoid" ? 0.25 : 1.0;
    return new THREE.MeshStandardMaterial({
      color: baseColor.clone().multiplyScalar(dim),
      emissive: baseColor,
      // Much lower emissive intensity — was 1.4, now 0.55. Stops the orb
      // from bleeding into a halo cloud.
      emissiveIntensity: visual.glow * 0.55 * dim,
      roughness: 0.45,
      metalness: 0.0,
      transparent: false,
      // Body stays tone-mapped now so its color doesn't exceed 1.0 and
      // contribute extra bloom. Halo is the only thing that pushes past 1.0.
      toneMapped: true,
    });
  }, [visual.color, visual.glow, dominantAnnotation?.kind]);

  // Smooth lerp scale + halo intensity in useFrame so transitions feel buttery.
  const groupRef = useRef<THREE.Group>(null);
  const targetScale = selected ? 1.16 : hovered ? 1.06 : 1.0;
  useFrame((state, delta) => {
    if (!groupRef.current) return;
    const cur = groupRef.current.scale.x;
    const next = THREE.MathUtils.lerp(
      cur,
      targetScale,
      1 - Math.exp(-delta * 8),
    );
    groupRef.current.scale.setScalar(next);
    haloUniforms.uTime.value = state.clock.elapsedTime;
    // Lerp halo brightness toward the active target.
    const cur_int = haloUniforms.uIntensity.value as number;
    haloUniforms.uIntensity.value = THREE.MathUtils.lerp(
      cur_int,
      haloIntensity,
      1 - Math.exp(-delta * 6),
    );
  });

  // Geometry resolution.
  const segments = baseRadius >= 7 ? 64 : baseRadius >= 5 ? 48 : 36;

  // Label visibility.
  const labelVisible = computeLabelVisibility({
    node,
    zoomLevel,
    hovered,
    selected,
  });
  const labelOffset = radius * 1.7;

  return (
    <group
      ref={groupRef}
      position={position}
      onPointerDown={(e) => {
        e.stopPropagation();
        onPointerDownNode?.(node.id, e);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
        document.body.style.cursor = "grab";
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = "";
      }}
    >
      {/* Halo — soft default, brightens on hover/selection. */}
      <Sphere
        args={[radius * 1.15, segments, segments]}
        material={haloMaterial}
        renderOrder={0}
      />

      {/* Body. */}
      <Sphere
        args={[radius, segments, segments]}
        material={bodyMaterial}
        renderOrder={1}
      />

      {/* Hover ring — affordance before click. Doesn't glow, just a thin
          line, so it reads as "interactive thing" not "important thing". */}
      {hovered && !selected && (
        <mesh rotation={[Math.PI / 2, 0, 0]} renderOrder={2}>
          <torusGeometry args={[radius * 1.4, 0.08, 12, 64]} />
          <meshBasicMaterial
            color="#ffffff"
            transparent
            opacity={0.5}
            toneMapped={false}
          />
        </mesh>
      )}

      {/* Selection ring — solid + branded color. */}
      {selected && (
        <mesh rotation={[Math.PI / 2, 0, 0]} renderOrder={2}>
          <torusGeometry args={[radius * 1.7, 0.14, 16, 96]} />
          <meshBasicMaterial
            color={visual.hex}
            transparent
            opacity={0.95}
            toneMapped={false}
          />
        </mesh>
      )}

      {/* Multi-select ring — thinner + cyan, drawn outside the selection
          ring so both can show simultaneously. */}
      {inMultiSelection && !selected && (
        <mesh rotation={[Math.PI / 2, 0, 0]} renderOrder={2}>
          <torusGeometry args={[radius * 1.55, 0.09, 12, 64]} />
          <meshBasicMaterial
            color="#22d3ee"
            transparent
            opacity={0.85}
            toneMapped={false}
          />
        </mesh>
      )}

      {/* Annotation ring — visible whenever the user has tagged this orb. */}
      {dominantAnnotation && (
        <mesh rotation={[Math.PI / 2, 0, 0]} renderOrder={3}>
          <torusGeometry args={[radius * 1.95, 0.16, 16, 96]} />
          <meshBasicMaterial
            color={ANNOTATION_RING_COLORS[dominantAnnotation.kind]}
            transparent
            opacity={0.85}
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

const ANNOTATION_RING_COLORS: Record<string, string> = {
  avoid: "#fb7185",   // rose-400 — "stop"
  focus: "#fbbf24",   // amber-400 — "look here"
  done:  "#34d399",   // emerald-400 — "complete"
  note:  "#7dd3fc",   // sky-300 — "info"
};

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
  if (zoomLevel <= 2) return true;
  if (zoomLevel === 3) {
    if (node.type.startsWith("goal.")) return true;
    if (node.type.startsWith("subagent.")) return true;
    if (node.type.endsWith(".failed")) return true;
    if (node.onCriticalPath) return true;
    return false;
  }
  return false;
}
