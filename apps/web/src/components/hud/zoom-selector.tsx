"use client";

import { useExplorerStore } from "@/lib/store";
import type { ZoomLevel } from "@/lib/types";

const LEVELS: Array<{ level: ZoomLevel; label: string; sub: string }> = [
  { level: 1, label: "L1", sub: "mission" },
  { level: 2, label: "L2", sub: "task" },
  { level: 3, label: "L3", sub: "operation" },
  { level: 4, label: "L4", sub: "raw" },
];

export function ZoomSelector() {
  const zoomLevel = useExplorerStore((s) => s.zoomLevel);
  const setZoomLevel = useExplorerStore((s) => s.setZoomLevel);
  const hideNoise = useExplorerStore((s) => s.hideNoise);
  const setHideNoise = useExplorerStore((s) => s.setHideNoise);

  return (
    <div className="glass flex flex-col gap-3 px-3 py-3 text-xs text-zinc-300">
      <div className="flex items-center gap-1">
        {LEVELS.map(({ level, label, sub }) => (
          <button
            key={level}
            type="button"
            onClick={() => setZoomLevel(level)}
            className={`flex flex-col items-center rounded-md px-3 py-1.5 transition ${
              zoomLevel === level
                ? "bg-white/10 text-zinc-100 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.1)]"
                : "text-zinc-400 hover:bg-white/5"
            }`}
            aria-label={`Zoom level ${level} — ${sub} view`}
          >
            <span className="font-semibold tracking-wide">{label}</span>
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">
              {sub}
            </span>
          </button>
        ))}
      </div>

      <label className="flex cursor-pointer items-center gap-2 text-[11px] text-zinc-400">
        <input
          type="checkbox"
          checked={hideNoise}
          onChange={(e) => setHideNoise(e.target.checked)}
          className="h-3.5 w-3.5 rounded border-white/15 bg-black/40 text-violet-500 focus:ring-violet-500/40"
        />
        Hide noise (salience &lt; 0.10)
      </label>
    </div>
  );
}
