"use client";

/**
 * Multi-select toolbar — shown only when 2+ orbs are selected.
 *
 * Lets the user bulk-tag a whole region of the cognitive graph in one
 * click. This is the "select all the dead-ends and mark them avoid in
 * one shot" workflow — much faster than clicking each node individually.
 *
 * Hides itself when fewer than two nodes are selected; the single-node
 * detail panel handles that case.
 */

import { useState } from "react";

import {
  createAnnotationsBatch,
  type AnnotationKind,
} from "@/lib/api";
import { useExplorerStore } from "@/lib/store";

interface MultiSelectToolbarProps {
  runId: string;
}

const KINDS: Array<{
  kind: AnnotationKind;
  label: string;
  color: string;
  hover: string;
  fg: string;
}> = [
  {
    kind: "avoid",
    label: "Avoid",
    color: "border-rose-400/30",
    hover: "hover:bg-rose-500/15 hover:border-rose-400/60",
    fg: "text-rose-300",
  },
  {
    kind: "focus",
    label: "Focus",
    color: "border-amber-400/30",
    hover: "hover:bg-amber-500/15 hover:border-amber-400/60",
    fg: "text-amber-300",
  },
  {
    kind: "done",
    label: "Done",
    color: "border-emerald-400/30",
    hover: "hover:bg-emerald-500/15 hover:border-emerald-400/60",
    fg: "text-emerald-300",
  },
];

export function MultiSelectToolbar({ runId }: MultiSelectToolbarProps) {
  const selectedNodeIds = useExplorerStore((s) => s.selectedNodeIds);
  const clearMultiSelection = useExplorerStore((s) => s.clearMultiSelection);
  const addAnnotations = useExplorerStore((s) => s.addAnnotations);

  const [busy, setBusy] = useState(false);

  if (selectedNodeIds.size < 2) return null;

  const onBulkTag = async (kind: AnnotationKind) => {
    if (busy) return;
    setBusy(true);
    try {
      const items = Array.from(selectedNodeIds).map((nodeId) => ({
        nodeId,
        kind,
      }));
      const resp = await createAnnotationsBatch(runId, items);
      addAnnotations(resp.items);
      clearMultiSelection();
    } catch (e) {
      console.error("bulk annotate failed", e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      role="toolbar"
      aria-label="Multi-select actions"
      className="glass-strong flex items-center gap-2 px-3 py-2 text-sm"
    >
      <span className="font-medium text-zinc-200">
        {selectedNodeIds.size} selected
      </span>
      <span className="h-4 w-px bg-white/10" />
      <span className="text-xs text-zinc-500">Tag all as:</span>
      {KINDS.map(({ kind, label, color, hover, fg }) => (
        <button
          key={kind}
          type="button"
          disabled={busy}
          onClick={() => onBulkTag(kind)}
          className={`rounded-md border ${color} ${hover} bg-transparent px-2.5 py-1 text-xs font-medium ${fg} transition disabled:opacity-50`}
        >
          {label}
        </button>
      ))}
      <span className="h-4 w-px bg-white/10" />
      <button
        type="button"
        onClick={clearMultiSelection}
        disabled={busy}
        className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-zinc-400 hover:bg-white/5 hover:text-zinc-200 disabled:opacity-50"
      >
        Clear
      </button>
    </div>
  );
}
