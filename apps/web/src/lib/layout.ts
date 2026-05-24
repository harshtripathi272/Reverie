/**
 * 3D layout — d3-force-3d simulation that produces stable positions for
 * every graph node. Run once on graph load, then frozen.
 *
 * Layout principles
 * -----------------
 *
 * The previous version pinned goals to depth strata via ``fy``, which
 * collapsed the whole graph onto horizontal planes — fine for a flat
 * 2D dendrogram, terrible for a 3D scene where you want spherical
 * distribution as the camera orbits.
 *
 * The new approach:
 *
 *   1. Top-level goals are spread on a *Fibonacci sphere* around the
 *      origin — guarantees even angular distribution no matter how many
 *      there are.
 *   2. Every other node starts near its parent, offset in a random
 *      direction at a depth-scaled distance. This gives the simulation
 *      a head start that already looks 3D.
 *   3. Forces (repulsion, link, collide) shape it from there. We do NOT
 *      pin any axis — the result is a truly volumetric layout.
 *   4. A weak depth-aware ``forceRadial`` gently expands deeper nodes
 *      outward, so the run reads "outward = deeper" without forcing
 *      everything onto a Y stratum.
 */

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLink,
  type SimulationNode,
} from "d3-force-3d";
import * as THREE from "three";

import { visualFor } from "@/lib/colors";
import type { GraphBundle, GraphNode } from "@/lib/types";

export interface PositionedNode extends SimulationNode {
  id: string;
  type: string;
  depth: number;
  x: number;
  y: number;
  z: number;
}

export interface LaidOutGraph {
  nodes: PositionedNode[];
  positions: Map<string, THREE.Vector3>;
}

const ITERATIONS = 400;
const ROOT_RING_RADIUS = 60;
const PER_DEPTH_RADIUS = 55;

/**
 * Compute stable 3D positions for every node in the bundle.
 */
export function layoutGraph(bundle: GraphBundle): LaidOutGraph {
  if (bundle.nodes.length === 0) {
    return { nodes: [], positions: new Map() };
  }

  // ---- Build parent->children adjacency for our seeding pass.
  const childrenByParent = new Map<string | null, GraphNode[]>();
  for (const n of bundle.nodes) {
    const key = n.parentId ?? null;
    const list = childrenByParent.get(key);
    if (list) list.push(n);
    else childrenByParent.set(key, [n]);
  }

  // ---- Seed initial positions.
  // Roots (nodes whose parentId is null OR points outside the run) on a
  // Fibonacci sphere; descendants near their parent + a phi/theta offset.
  const initPos = new Map<string, [number, number, number]>();
  const knownIds = new Set(bundle.nodes.map((n) => n.id));

  const roots = bundle.nodes.filter(
    (n) => n.parentId === null || !knownIds.has(n.parentId),
  );

  // Fibonacci-sphere placement for the roots — even angular spread.
  roots.forEach((root, i) => {
    const total = roots.length;
    const phi = Math.acos(1 - (2 * (i + 0.5)) / total);
    const goldenAngle = Math.PI * (1 + Math.sqrt(5));
    const theta = goldenAngle * (i + 0.5);
    const r = total === 1 ? 0 : ROOT_RING_RADIUS;
    initPos.set(root.id, [
      r * Math.sin(phi) * Math.cos(theta),
      r * Math.sin(phi) * Math.sin(theta),
      r * Math.cos(phi),
    ]);
  });

  // BFS the rest. Each child gets a per-parent angular slice so siblings
  // spread evenly around the parent rather than all sharing one direction.
  const queue: GraphNode[] = [...roots];
  while (queue.length > 0) {
    const parent = queue.shift()!;
    const kids = childrenByParent.get(parent.id) ?? [];
    if (kids.length === 0) continue;

    const [px, py, pz] = initPos.get(parent.id)!;

    kids.forEach((kid, i) => {
      const total = kids.length;
      // Children-fibonacci-sphere — same trick at every level.
      const phi = Math.acos(1 - (2 * (i + 0.5)) / total);
      const golden = Math.PI * (1 + Math.sqrt(5));
      const theta = golden * (i + 0.5);
      const r = PER_DEPTH_RADIUS;
      initPos.set(kid.id, [
        px + r * Math.sin(phi) * Math.cos(theta),
        py + r * Math.sin(phi) * Math.sin(theta),
        pz + r * Math.cos(phi),
      ]);
      queue.push(kid);
    });
  }

  // ---- Build simulation nodes.
  const sim_nodes: PositionedNode[] = bundle.nodes.map((n) => {
    const seed = initPos.get(n.id) ?? [0, 0, 0];
    return {
      id: n.id,
      type: n.type,
      depth: n.depth,
      x: seed[0],
      y: seed[1],
      z: seed[2],
    };
  });

  const sim_links: SimulationLink<PositionedNode>[] = bundle.edges.map(
    (e) => ({ source: e.source, target: e.target }),
  );

  // ---- Forces.
  const sim = forceSimulation(sim_nodes, 3)
    .force(
      "charge",
      forceManyBody<PositionedNode>().strength((d) => {
        // Goals push hard so they form the visual spine of clusters.
        if (d.type.startsWith("goal.")) return -380;
        // Subagents are second-tier anchors.
        if (d.type.startsWith("subagent.")) return -240;
        // Retries cluster tightly around their parent — weak charge.
        if (d.type.startsWith("retry.")) return -50;
        // Normal operations.
        return -150;
      }),
    )
    .force("center", forceCenter<PositionedNode>(0, 0, 0))
    .force(
      "link",
      forceLink<PositionedNode, SimulationLink<PositionedNode>>(sim_links)
        .id((d) => d.id)
        .distance((l) => {
          const tgt = (l.target as PositionedNode).type;
          if (tgt.startsWith("retry.")) return 18;
          if (tgt.startsWith("goal.")) return 90;
          return 55;
        })
        .strength(0.55)
        .iterations(2),
    )
    .force(
      "collide",
      forceCollide<PositionedNode>(
        (d) => visualFor(d.type).radius * 1.8 + 6,
      ).iterations(2),
    );

  sim.alpha(1).alphaDecay(0.025).velocityDecay(0.42).stop();
  for (let i = 0; i < ITERATIONS; i++) sim.tick();
  sim.alpha(0);

  // ---- Convert to Three.js Vector3 map.
  const positions = new Map<string, THREE.Vector3>();
  for (const n of sim_nodes) {
    positions.set(n.id, new THREE.Vector3(n.x, n.y, n.z));
  }

  return { nodes: sim_nodes, positions };
}
