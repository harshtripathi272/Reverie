"use client";

import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";

import { visualFor } from "@/lib/colors";
import type { GraphEdge, GraphNode } from "@/lib/types";

/**
 * Bezier tube connection between parent and child. Critical-path edges get:
 *   - thicker tube
 *   - target-color tint (instead of dim white)
 *   - flowing particles along the tube
 */

interface ConnectionProps {
  edge: GraphEdge;
  source: THREE.Vector3;
  target: THREE.Vector3;
  targetNode: GraphNode | undefined;
  showFlow: boolean;
}

const TUBE_SEGMENTS = 28;

export function Connection({
  edge,
  source,
  target,
  targetNode,
  showFlow,
}: ConnectionProps) {
  const isCritical = edge.onCriticalPath;
  const visual = targetNode ? visualFor(targetNode.type) : visualFor("unknown");

  // Curve: midpoint pulled toward the orbit halfway between, with a slight
  // outward bow so edges don't perfectly stack on each other.
  const curve = useMemo(() => {
    const mid = source.clone().add(target).multiplyScalar(0.5);
    // Bow out perpendicular to the source→target axis. Stable per edge.
    const dir = target.clone().sub(source);
    const len = Math.max(dir.length(), 1e-3);
    const bowAxis =
      Math.abs(dir.y) > 0.9 * len
        ? new THREE.Vector3(1, 0, 0)
        : new THREE.Vector3(0, 1, 0);
    const bow = new THREE.Vector3()
      .crossVectors(dir, bowAxis)
      .normalize()
      .multiplyScalar(len * 0.12);
    mid.add(bow);
    return new THREE.QuadraticBezierCurve3(source, mid, target);
  }, [source, target]);

  const tubeGeometry = useMemo(
    () =>
      new THREE.TubeGeometry(
        curve,
        TUBE_SEGMENTS,
        isCritical ? 0.5 : 0.18,
        8,
        false,
      ),
    [curve, isCritical],
  );

  const tubeMaterial = useMemo(() => {
    if (isCritical) {
      return new THREE.MeshBasicMaterial({
        color: visual.color,
        transparent: true,
        opacity: 0.85,
        toneMapped: false,
      });
    }
    return new THREE.MeshBasicMaterial({
      color: 0x9ca3af,
      transparent: true,
      opacity: 0.18,
    });
  }, [isCritical, visual.color]);

  // Flowing particles along critical paths during replay.
  const flowRef = useRef<THREE.Points>(null);
  const flowGeometry = useMemo(() => {
    if (!showFlow) return null;
    const count = 4;
    const positions = new Float32Array(count * 3);
    const offsets = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      offsets[i] = i / count;
      const p = curve.getPoint(offsets[i]);
      positions[i * 3 + 0] = p.x;
      positions[i * 3 + 1] = p.y;
      positions[i * 3 + 2] = p.z;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setAttribute("offset", new THREE.BufferAttribute(offsets, 1));
    return g;
  }, [curve, showFlow]);

  useFrame((state) => {
    if (!flowRef.current || !flowGeometry) return;
    const t = state.clock.elapsedTime * 0.4;
    const offsets = flowGeometry.getAttribute("offset");
    const positions = flowGeometry.getAttribute("position");
    for (let i = 0; i < offsets.count; i++) {
      let u = (offsets.array[i] + t) % 1;
      const p = curve.getPoint(u);
      positions.setXYZ(i, p.x, p.y, p.z);
    }
    positions.needsUpdate = true;
  });

  return (
    <>
      <mesh geometry={tubeGeometry} material={tubeMaterial} />
      {showFlow && flowGeometry && (
        <points ref={flowRef} geometry={flowGeometry}>
          <pointsMaterial
            color={visual.hex}
            size={isCritical ? 2.4 : 1.4}
            sizeAttenuation
            transparent
            opacity={0.9}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </points>
      )}
    </>
  );
}
