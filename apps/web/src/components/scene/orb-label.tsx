"use client";

import { Html } from "@react-three/drei";
import * as THREE from "three";

import type { GraphNode } from "@/lib/types";

/**
 * DOM-rendered label that follows an orb in 3D space.
 *
 * We use Drei's <Html> rather than baking text into a canvas because:
 *   - The text stays crisp at any zoom level (no MIPMAP fuzz).
 *   - We get free CSS — backdrop blur, text shadow, ellipsis truncation.
 *   - Hit-testing isn't a concern because the parent <Orb> already handles
 *     pointer events on its sphere geometry.
 *
 * Important: ``occlude`` is intentionally OFF. With occlude, labels behind
 * orbs from the camera's POV vanish — which on a dense cluster strobes
 * confusingly. Better to let labels overlap and rely on z-order.
 */

interface OrbLabelProps {
  node: GraphNode;
  /** Offset from the orb center, in world units. Lifted so it floats above. */
  offset: number;
  /**
   * Whether this label should currently be visible. Visibility is computed
   * higher up so the rules can vary by zoom level / hover / selection.
   */
  visible: boolean;
  /** Highlighted (hovered or selected) labels render slightly differently. */
  emphasised?: boolean;
}

export function OrbLabel({
  node,
  offset,
  visible,
  emphasised = false,
}: OrbLabelProps) {
  if (!visible) return null;

  const truncated = truncate(prettyLabel(node));

  return (
    <Html
      position={[0, offset, 0]}
      center
      // ``zIndexRange`` keeps labels behind any HUD elements which sit at
      // higher z-indexes in the parent component.
      zIndexRange={[10, 20]}
      // Make the label DOM transparent to clicks so the user can still
      // interact with the orb behind it.
      style={{
        pointerEvents: "none",
        userSelect: "none",
        whiteSpace: "nowrap",
      }}
      // ``distanceFactor`` would scale the label with depth; we deliberately
      // leave it off so labels stay legible regardless of camera distance.
    >
      <div
        className={
          emphasised
            ? "rounded-md border border-white/15 bg-black/75 px-2 py-1 text-[11px] font-medium text-zinc-100 backdrop-blur-md"
            : "rounded-md bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-zinc-300 backdrop-blur-sm"
        }
        style={{
          textShadow: "0 1px 2px rgba(0,0,0,0.6)",
          boxShadow: emphasised
            ? "0 0 0 1px rgba(255,255,255,0.05), 0 4px 12px rgba(0,0,0,0.45)"
            : undefined,
        }}
      >
        {truncated}
      </div>
    </Html>
  );
}

// ---------------------------------------------------------------------------
// Pretty labels
// ---------------------------------------------------------------------------

/**
 * Compact, screen-friendly text for a node. Falls back to the type when no
 * label is set (e.g. a fresh ingest before the renderer pulls payload data).
 */
function prettyLabel(node: GraphNode): string {
  // The backend already produces a one-liner via build._label which is
  // cleaner than the raw type. Use it when present.
  if (node.label && node.label.trim().length > 0) return node.label;
  return node.type;
}

function truncate(s: string, max = 28): string {
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1)}…`;
}
