"use client";

/**
 * Color legend — keeps users from having to remember "violet = goal".
 *
 * Sits in the bottom-left of the explorer. Compact by default; click to
 * expand the full list. Uses the same palette as the scene (pulled from
 * lib/colors so any palette change shows up here automatically).
 */

import { useState } from "react";

const ENTRIES: Array<{ hex: string; label: string; sub?: string }> = [
  { hex: "#7C3AED", label: "Goal", sub: "intent / subtask" },
  { hex: "#0EA5E9", label: "Tool call", sub: "search, read, write..." },
  { hex: "#10B981", label: "Memory", sub: "retrieval / store" },
  { hex: "#06B6D4", label: "Subagent", sub: "delegation" },
  { hex: "#8B5CF6", label: "Reasoning", sub: "model thought" },
  { hex: "#F59E0B", label: "Retry", sub: "warning / pulses" },
  { hex: "#22C55E", label: "Validation", sub: "passed check" },
  { hex: "#EF4444", label: "Failure", sub: "intense glow" },
];

export function Legend() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="glass flex flex-col gap-2 px-3 py-2.5 text-xs">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center justify-between gap-3 text-left text-zinc-400 transition hover:text-zinc-200"
      >
        <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
          Legend
        </span>
        <span className="text-[10px] text-zinc-500">
          {expanded ? "hide" : "show"}
        </span>
      </button>

      {expanded && (
        <div className="grid grid-cols-1 gap-1.5 pt-1">
          {ENTRIES.map((e) => (
            <div key={e.label} className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 flex-shrink-0 rounded-full"
                style={{
                  backgroundColor: e.hex,
                  boxShadow: `0 0 6px ${e.hex}`,
                }}
              />
              <div className="leading-tight">
                <div className="text-zinc-200">{e.label}</div>
                {e.sub && (
                  <div className="text-[10px] text-zinc-500">{e.sub}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {!expanded && (
        <div className="flex items-center gap-1.5">
          {ENTRIES.slice(0, 5).map((e) => (
            <span
              key={e.hex}
              className="h-2.5 w-2.5 rounded-full"
              style={{
                backgroundColor: e.hex,
                boxShadow: `0 0 5px ${e.hex}`,
              }}
              title={e.label}
            />
          ))}
          <span className="text-[10px] text-zinc-500">+more</span>
        </div>
      )}
    </div>
  );
}
