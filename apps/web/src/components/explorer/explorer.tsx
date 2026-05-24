"use client";

import { useEffect, useMemo, useState } from "react";

import { Header } from "@/components/hud/header";
import { Legend } from "@/components/hud/legend";
import { LoadingOverlay } from "@/components/hud/loading-overlay";
import { NodeDetailPanel } from "@/components/hud/node-detail";
import { RunStats } from "@/components/hud/run-stats";
import { ViewControls } from "@/components/hud/view-controls";
import { ZoomSelector } from "@/components/hud/zoom-selector";
import { Scene } from "@/components/scene/scene";
import { getRun, getSalienceGraph } from "@/lib/api";
import { layoutGraph, type LaidOutGraph } from "@/lib/layout";
import { useExplorerStore } from "@/lib/store";
import type { GraphBundle, Run } from "@/lib/types";

interface ExplorerProps {
  runId: string;
}

export function Explorer({ runId }: ExplorerProps) {
  const [run, setRun] = useState<Run | null>(null);
  const [bundle, setBundle] = useState<GraphBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [graphLoading, setGraphLoading] = useState(true);

  const zoomLevel = useExplorerStore((s) => s.zoomLevel);
  const hideNoise = useExplorerStore((s) => s.hideNoise);

  // Fetch run metadata (stable across zoom changes).
  useEffect(() => {
    let cancelled = false;
    setRun(null);
    setError(null);
    getRun(runId)
      .then((r) => !cancelled && setRun(r))
      .catch((e) => !cancelled && setError(e?.message ?? String(e)));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  // Fetch the salience-scored graph each time zoom or noise filter changes.
  useEffect(() => {
    let cancelled = false;
    setBundle(null);
    setGraphLoading(true);
    getSalienceGraph(runId, { level: zoomLevel, hideNoise })
      .then((g) => {
        if (cancelled) return;
        setBundle(g);
        setGraphLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? String(e));
        setGraphLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, zoomLevel, hideNoise]);

  // Re-run the layout whenever the graph changes.
  const layout: LaidOutGraph | null = useMemo(
    () => (bundle ? layoutGraph(bundle) : null),
    [bundle],
  );

  return (
    <div className="relative h-screen w-screen bg-black">
      {/* The 3D scene is the base layer — the HUD overlays it. */}
      <Scene bundle={bundle} layout={layout} />

      {/* HUD ----------------------------------------------------------- */}
      <div className="pointer-events-none absolute inset-0 flex flex-col">
        <div className="pointer-events-auto">
          <Header
            middle={
              run && (
                <div className="flex items-center justify-center gap-3 text-sm text-zinc-300">
                  <span className="truncate font-medium">
                    {run.goal ?? "(untitled)"}
                  </span>
                  <span className="text-xs text-zinc-500">
                    {run.totalEvents} events
                  </span>
                </div>
              )
            }
            right={
              <div className="pointer-events-auto flex items-center gap-3">
                <span className="text-xs text-zinc-500">
                  {bundle
                    ? `${bundle.summary.totalNodes} nodes`
                    : "loading…"}
                </span>
                <ViewControls />
              </div>
            }
          />
        </div>

        <div className="flex flex-1 flex-col justify-between p-4">
          {/* Top row: stats top-right. */}
          <div className="flex items-start justify-end">
            <div className="pointer-events-auto">
              {bundle && <RunStats bundle={bundle} />}
            </div>
          </div>

          {/* Bottom row: legend on the left, zoom selector on the right. */}
          <div className="flex items-end justify-between gap-3">
            <div className="pointer-events-auto">
              <Legend />
            </div>
            <div className="pointer-events-auto">
              <ZoomSelector />
            </div>
          </div>
        </div>
      </div>

      {/* Node detail slides in from the right. */}
      <div className="pointer-events-auto absolute right-4 top-20 z-20 max-h-[calc(100vh-6rem)]">
        {bundle && <NodeDetailPanel bundle={bundle} />}
      </div>

      {/* Loading overlay — only shown while we're waiting for the first
          graph payload. Subsequent zoom-level switches don't re-trigger it
          so the experience feels snappy. */}
      {graphLoading && !bundle && !error && (
        <LoadingOverlay message="Reconstructing cognition..." />
      )}

      {/* Error overlay. */}
      {error && (
        <div className="pointer-events-auto absolute left-1/2 top-1/2 z-30 w-[28rem] -translate-x-1/2 -translate-y-1/2">
          <div className="glass-strong p-5 text-sm text-rose-300">
            <strong>Could not load run.</strong>
            <p className="mt-1 text-zinc-400">{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}
