"use client";

import { visualFor } from "@/lib/colors";
import { formatDuration, formatTimestamp, shortId } from "@/lib/format";
import { useExplorerStore } from "@/lib/store";
import type { GraphBundle, GraphNode } from "@/lib/types";

interface NodeDetailPanelProps {
  bundle: GraphBundle;
}

export function NodeDetailPanel({ bundle }: NodeDetailPanelProps) {
  const selectedNodeId = useExplorerStore((s) => s.selectedNodeId);
  const setSelectedNodeId = useExplorerStore((s) => s.setSelectedNodeId);

  if (selectedNodeId == null) return null;

  const node: GraphNode | undefined = bundle.nodes.find(
    (n) => n.id === selectedNodeId,
  );
  if (!node) return null;

  const visual = visualFor(node.type);
  const salience = node.salience ?? 0;
  const sailbar = Math.max(0, Math.min(1, salience)) * 100;

  return (
    <aside
      role="dialog"
      aria-label="Event detail"
      className="glass-strong w-80 animate-fade-in flex-col gap-3 p-4 text-sm"
    >
      <header className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{
                backgroundColor: visual.hex,
                boxShadow: `0 0 8px ${visual.hex}`,
              }}
            />
            <code className="font-mono text-xs text-zinc-300">
              {node.type}
            </code>
          </div>
          <h2 className="mt-1.5 text-base font-medium leading-tight text-zinc-100">
            {node.label || "(no label)"}
          </h2>
        </div>
        <button
          type="button"
          onClick={() => setSelectedNodeId(null)}
          className="rounded p-1 text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
          aria-label="Close detail"
        >
          ×
        </button>
      </header>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <span className="text-zinc-500">id</span>
        <code className="font-mono text-zinc-300">{shortId(node.id, 12)}</code>

        <span className="text-zinc-500">depth</span>
        <span className="text-zinc-300">{node.depth}</span>

        <span className="text-zinc-500">timestamp</span>
        <span className="text-zinc-300">{formatTimestamp(node.timestamp)}</span>

        <span className="text-zinc-500">duration</span>
        <span className="text-zinc-300">
          {formatDuration(node.durationMs ?? null)}
        </span>

        <span className="text-zinc-500">zoom level</span>
        <span className="text-zinc-300">L{node.zoomLevel}</span>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="text-zinc-500">salience</span>
          <span className="text-zinc-300">{salience.toFixed(2)}</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${sailbar}%`,
              background: `linear-gradient(90deg, ${visual.hex}AA, ${visual.hex})`,
              boxShadow: `0 0 8px ${visual.hex}`,
            }}
          />
        </div>
      </div>

      {node.onCriticalPath && (
        <div className="rounded-md border border-rose-400/30 bg-rose-500/10 px-2.5 py-1.5 text-xs text-rose-200">
          On critical path
        </div>
      )}

      {node.anomalies.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs uppercase tracking-wider text-zinc-500">
            Anomalies
          </div>
          {node.anomalies.map((a, i) => (
            <div
              key={i}
              className="rounded-md border border-amber-400/20 bg-amber-500/5 px-2.5 py-1.5"
            >
              <div className="text-xs font-semibold uppercase text-amber-300">
                {a.kind}
              </div>
              <div className="text-xs text-zinc-300">{a.detail}</div>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
