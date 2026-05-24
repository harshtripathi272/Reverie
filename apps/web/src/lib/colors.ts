/**
 * Per-event-type color palette. Pulled directly from the SRS Layer 8 spec.
 *
 * Returned as both:
 *   - a CSS hex string for HUD tints
 *   - a THREE.Color-friendly RGB tuple for the orb shader
 */

import * as THREE from "three";

export interface EventVisual {
  hex: string;
  color: THREE.Color;
  // Bloom intensity multiplier — failures pop more than goals.
  glow: number;
  // Base radius scaling — goals are biggest.
  radius: number;
}

const PALETTE: Record<string, EventVisual> = {
  "goal.created": v("#7C3AED", 1.0, 8),
  "goal.completed": v("#7C3AED", 0.9, 7),
  "goal.failed": v("#EF4444", 1.6, 8),
  "tool.called": v("#0EA5E9", 0.8, 5),
  "tool.returned": v("#0EA5E9", 0.7, 4),
  "tool.failed": v("#EF4444", 1.4, 5),
  "memory.retrieved": v("#10B981", 0.8, 5),
  "memory.stored": v("#10B981", 0.7, 4),
  "retry.triggered": v("#F59E0B", 1.1, 4),
  "retry.exhausted": v("#EF4444", 1.4, 5),
  "reflection.generated": v("#8B5CF6", 0.7, 4),
  "subagent.spawned": v("#06B6D4", 1.0, 6),
  "subagent.completed": v("#06B6D4", 0.8, 5),
  "validation.passed": v("#22C55E", 0.6, 3),
  "validation.failed": v("#EF4444", 1.2, 4),
  "context.truncated": v("#F59E0B", 0.8, 4),
  "planner.updated": v("#8B5CF6", 0.7, 4),
  "reasoning.extracted": v("#8B5CF6", 0.6, 3),
};

const FALLBACK = v("#6B7280", 0.4, 3);

function v(hex: string, glow: number, radius: number): EventVisual {
  return {
    hex,
    color: new THREE.Color(hex),
    glow,
    radius,
  };
}

export function visualFor(type: string): EventVisual {
  return PALETTE[type] ?? FALLBACK;
}

/**
 * Salience-modulated radius. Per SRS the multiplier is 1.0–2.5x.
 */
export function radiusFromSalience(base: number, salience: number | null): number {
  if (salience == null) return base;
  return base * (1.0 + Math.min(1.5, Math.max(0, salience) * 1.5));
}
