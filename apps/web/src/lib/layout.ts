/**
 * 3D layout — d3-force-3d simulation that produces stable positions for
 * every graph node. Run once on graph load, then frozen.
 *
 * Layout principles (per SRS Layer 8):
 *
 *   - Goal nodes are *fixed* on a vertical axis (root at y=0, descendants
 *     stratified by depth). Their orbits become the spine of the run.
 *   - Tool / memory / leaf nodes orbit their parents in a loose sphere via
 *     forceManyBody repulsion.
 *   - Retry nodes cluster tightly (low repulsion) around their parent tool.
 *   - The simulation runs for 300 iterations and stops; we don't keep ticking.
 */

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceY,
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

const ITERATIONS = 300;
const Y_PER_DEPTH = 100;

/**
 * Compute stable 3D positions for every node in the bundle.
 *
 * Returns both a parallel array and a Map keyed by event id — components
 * use the map for O(1) lookup when laying out edges.
 */
export function layoutGraph(bundle: GraphBundle): LaidOutGraph {
  const sim_nodes: PositionedNode[] = bundle.nodes.map((n) => ({
    id: n.id,
    type: n.type,
    depth: n.depth,
    x: 0,
    y: -n.depth * Y_PER_DEPTH,
    z: 0,
    // Goal nodes are pinned to their depth strata so the run reads
    // top-down at a glance. Other nodes float free.
    fy: n.type.startsWith("goal.") ? -n.depth * Y_PER_DEPTH : null,
  }));

  const sim_links: SimulationLink<PositionedNode>[] = bundle.edges.map(
    (e) => ({ source: e.source, target: e.target }),
  );

  // Seed positions deterministically — same bundle in twice produces the same
  // layout. Otherwise R3F users would see the orbs drift between reloads.
  for (let i = 0; i < sim_nodes.length; i++) {
    const seed = i * 137.508; // golden-angle pseudo-random
    sim_nodes[i].x = Math.cos(seed) * 60;
    sim_nodes[i].z = Math.sin(seed) * 60;
  }

  const sim = forceSimulation(sim_nodes, 3)
    .force(
      "charge",
      forceManyBody<PositionedNode>().strength((d) => {
        // Goals push hard (they're the spine); leaves push less.
        if (d.type.startsWith("goal.")) return -260;
        if (d.type.startsWith("retry.")) return -40; // tight cluster
        return -120;
      }),
    )
    .force("center", forceCenter<PositionedNode>(0, 0, 0))
    .force(
      "link",
      forceLink<PositionedNode, SimulationLink<PositionedNode>>(sim_links)
        .id((d) => d.id)
        .distance((l) => {
          const src = (l.source as PositionedNode).type;
          const tgt = (l.target as PositionedNode).type;
          if (tgt.startsWith("retry.")) return 16;
          if (src.startsWith("goal.") && tgt.startsWith("goal.")) return 90;
          return 50;
        })
        .strength(0.5)
        .iterations(2),
    )
    .force(
      "collide",
      forceCollide<PositionedNode>(
        (d) => visualFor(d.type).radius * 1.6 + 4,
      ).iterations(2),
    )
    // Pull toward the depth stratum even for non-goal nodes — keeps the
    // overall shape readable instead of a chaotic blob.
    .force(
      "y",
      forceY<PositionedNode>((d) => -d.depth * Y_PER_DEPTH).strength(0.15),
    );

  sim.alpha(1).alphaDecay(0.03).velocityDecay(0.4).stop();
  for (let i = 0; i < ITERATIONS; i++) sim.tick();

  // Stop the simulation explicitly — we never want it to keep ticking.
  sim.alpha(0);

  const positions = new Map<string, THREE.Vector3>();
  for (const n of sim_nodes) {
    positions.set(n.id, new THREE.Vector3(n.x, n.y, n.z));
  }

  return { nodes: sim_nodes, positions };
}
