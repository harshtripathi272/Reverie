/**
 * Client state for the explorer view — selection, zoom level, annotations.
 *
 * The graph itself comes from the server and lives in component-local state
 * (one fetch per route navigation). Only ephemeral UI state and the
 * annotation cache go in Zustand.
 */

import { create } from "zustand";

import type { Annotation, AnnotationKind } from "@/lib/api";
import type { ZoomLevel } from "@/lib/types";

interface ExplorerState {
  /** Single selected node — used by the detail panel and frame-camera. */
  selectedNodeId: string | null;
  /**
   * Multi-selection set used for bulk-tag operations. The single-select
   * ``selectedNodeId`` is always included in this set when set; clearing
   * single also clears multi.
   */
  selectedNodeIds: Set<string>;
  zoomLevel: ZoomLevel;
  hideNoise: boolean;
  isPlaying: boolean;
  /**
   * Pulse counter incremented whenever something requests the camera reset
   * to its initial framing. The scene watches this and runs a smooth dolly.
   */
  cameraResetTick: number;
  /**
   * Pulse counter incremented to ask the scene to fly the camera to the
   * currently selected node.
   */
  frameSelectedTick: number;

  /** Annotation cache — keyed by node id, list of annotations on that node. */
  annotationsByNode: Map<string, Annotation[]>;

  /** Right-click context menu position; null = hidden. */
  contextMenu: {
    x: number;
    y: number;
    nodeId: string;
  } | null;

  setSelectedNodeId: (id: string | null) => void;
  toggleNodeInSelection: (id: string) => void;
  clearMultiSelection: () => void;
  setZoomLevel: (level: ZoomLevel) => void;
  setHideNoise: (v: boolean) => void;
  setPlaying: (v: boolean) => void;
  resetCamera: () => void;
  frameSelected: () => void;

  setAnnotations: (annotations: Annotation[]) => void;
  addAnnotations: (annotations: Annotation[]) => void;
  removeAnnotation: (annotationId: string) => void;

  openContextMenu: (x: number, y: number, nodeId: string) => void;
  closeContextMenu: () => void;
}

function indexByNode(annotations: Annotation[]): Map<string, Annotation[]> {
  const map = new Map<string, Annotation[]>();
  for (const a of annotations) {
    const list = map.get(a.nodeId) ?? [];
    list.push(a);
    map.set(a.nodeId, list);
  }
  return map;
}

export const useExplorerStore = create<ExplorerState>((set) => ({
  selectedNodeId: null,
  selectedNodeIds: new Set(),
  // Default to operation view — usually the most informative for a fresh user.
  zoomLevel: 3,
  hideNoise: false,
  isPlaying: false,
  cameraResetTick: 0,
  frameSelectedTick: 0,
  annotationsByNode: new Map(),
  contextMenu: null,

  setSelectedNodeId: (id) =>
    set(() => ({
      selectedNodeId: id,
      selectedNodeIds: id ? new Set([id]) : new Set(),
    })),
  toggleNodeInSelection: (id) =>
    set((s) => {
      const next = new Set(s.selectedNodeIds);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      // Single-select tracker follows the most recently added node.
      const single = next.has(id) ? id : Array.from(next).pop() ?? null;
      return { selectedNodeIds: next, selectedNodeId: single };
    }),
  clearMultiSelection: () =>
    set({ selectedNodeIds: new Set(), selectedNodeId: null }),

  setZoomLevel: (level) => set({ zoomLevel: level }),
  setHideNoise: (v) => set({ hideNoise: v }),
  setPlaying: (v) => set({ isPlaying: v }),
  resetCamera: () => set((s) => ({ cameraResetTick: s.cameraResetTick + 1 })),
  frameSelected: () =>
    set((s) => ({ frameSelectedTick: s.frameSelectedTick + 1 })),

  setAnnotations: (annotations) =>
    set({ annotationsByNode: indexByNode(annotations) }),
  addAnnotations: (annotations) =>
    set((s) => {
      const next = new Map(s.annotationsByNode);
      for (const a of annotations) {
        const list = next.get(a.nodeId) ?? [];
        next.set(a.nodeId, [...list, a]);
      }
      return { annotationsByNode: next };
    }),
  removeAnnotation: (annotationId) =>
    set((s) => {
      const next = new Map<string, Annotation[]>();
      for (const [nodeId, list] of s.annotationsByNode) {
        const filtered = list.filter((a) => a.id !== annotationId);
        if (filtered.length > 0) next.set(nodeId, filtered);
      }
      return { annotationsByNode: next };
    }),

  openContextMenu: (x, y, nodeId) =>
    set({ contextMenu: { x, y, nodeId } }),
  closeContextMenu: () => set({ contextMenu: null }),
}));
