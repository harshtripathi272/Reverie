/**
 * Client state for the explorer view — selection, zoom level, salience filter.
 *
 * The graph itself comes from the server and lives in component-local state
 * (one fetch per route navigation). Only ephemeral UI state goes in Zustand.
 */

import { create } from "zustand";

import type { ZoomLevel } from "@/lib/types";

interface ExplorerState {
  selectedNodeId: string | null;
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
   * currently selected node. -1 means the action hasn't been requested yet.
   */
  frameSelectedTick: number;

  setSelectedNodeId: (id: string | null) => void;
  setZoomLevel: (level: ZoomLevel) => void;
  setHideNoise: (v: boolean) => void;
  setPlaying: (v: boolean) => void;
  resetCamera: () => void;
  frameSelected: () => void;
}

export const useExplorerStore = create<ExplorerState>((set) => ({
  selectedNodeId: null,
  // Default to operation view — usually the most informative for a fresh user.
  zoomLevel: 3,
  hideNoise: false,
  isPlaying: false,
  cameraResetTick: 0,
  frameSelectedTick: 0,
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),
  setZoomLevel: (level) => set({ zoomLevel: level }),
  setHideNoise: (v) => set({ hideNoise: v }),
  setPlaying: (v) => set({ isPlaying: v }),
  resetCamera: () =>
    set((s) => ({ cameraResetTick: s.cameraResetTick + 1 })),
  frameSelected: () =>
    set((s) => ({ frameSelectedTick: s.frameSelectedTick + 1 })),
}));
