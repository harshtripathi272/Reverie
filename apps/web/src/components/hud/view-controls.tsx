"use client";

import { useExplorerStore } from "@/lib/store";

/**
 * Camera-control toolbar. Two buttons:
 *
 *   - **Reset** — fly back to the bird's-eye fitted view of the whole graph.
 *   - **Frame** — fly to the currently-selected node (disabled if none).
 *
 * Both go through the store's pulse counters so the scene's CameraRig can
 * react via ``useEffect`` without us holding a direct ref to OrbitControls.
 */
export function ViewControls() {
  const resetCamera = useExplorerStore((s) => s.resetCamera);
  const frameSelected = useExplorerStore((s) => s.frameSelected);
  const selectedNodeId = useExplorerStore((s) => s.selectedNodeId);

  return (
    <div className="glass flex items-center gap-1 px-2 py-1.5 text-xs">
      <button
        type="button"
        onClick={resetCamera}
        className="rounded-md px-2.5 py-1 text-zinc-300 transition hover:bg-white/5 hover:text-zinc-100"
        title="Reset camera to fit"
      >
        Reset view
      </button>
      <span className="h-4 w-px bg-white/10" />
      <button
        type="button"
        onClick={frameSelected}
        disabled={!selectedNodeId}
        className="rounded-md px-2.5 py-1 text-zinc-300 transition hover:bg-white/5 hover:text-zinc-100 disabled:cursor-not-allowed disabled:text-zinc-600 disabled:hover:bg-transparent"
        title={
          selectedNodeId
            ? "Fly camera to selected node"
            : "Select a node first"
        }
      >
        Frame selected
      </button>
    </div>
  );
}
