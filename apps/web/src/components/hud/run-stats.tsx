"use client";

import type { GraphBundle } from "@/lib/types";

interface RunStatsProps {
  bundle: GraphBundle;
}

export function RunStats({ bundle }: RunStatsProps) {
  const { summary } = bundle;
  const anomalies = Object.entries(summary.anomaliesByKind);

  return (
    <div className="glass flex flex-col gap-1 px-4 py-3 text-xs">
      <div className="flex items-center gap-3 text-zinc-300">
        <span>
          <span className="text-zinc-500">L1</span>{" "}
          {summary.nodesPerZoom["1"] ?? 0}
        </span>
        <span>
          <span className="text-zinc-500">L2</span>{" "}
          {summary.nodesPerZoom["2"] ?? 0}
        </span>
        <span>
          <span className="text-zinc-500">L3</span>{" "}
          {summary.nodesPerZoom["3"] ?? 0}
        </span>
        <span>
          <span className="text-zinc-500">L4</span>{" "}
          {summary.nodesPerZoom["4"] ?? 0}
        </span>
      </div>
      <div className="flex items-center gap-3 text-zinc-400">
        <span>
          <span className="text-zinc-500">edges</span> {summary.totalEdges}
        </span>
        <span>
          <span className="text-zinc-500">critical</span>{" "}
          {summary.criticalPathLength}
        </span>
      </div>
      {anomalies.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center gap-1">
          {anomalies.map(([kind, count]) => (
            <span
              key={kind}
              className="rounded bg-amber-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-300"
            >
              {kind} ×{count}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
