"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listRuns } from "@/lib/api";
import { formatDuration, formatTimestamp, shortId } from "@/lib/format";
import type { Run } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  running: "text-amber-300",
  completed: "text-emerald-300",
  failed: "text-rose-300",
  aborted: "text-fuchsia-300",
};

export function RunsList() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const page = await listRuns({ limit: 50 });
        if (!cancelled) setRuns(page.items);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="glass p-5 text-sm text-rose-300">
        <strong>Backend unreachable.</strong>
        <p className="mt-1 text-zinc-400">{error}</p>
        <p className="mt-2 text-xs text-zinc-500">
          Start it with{" "}
          <code className="rounded bg-white/5 px-1 py-0.5">
            python -m reverie_api
          </code>{" "}
          and try again.
        </p>
      </div>
    );
  }

  if (runs == null) {
    return (
      <div className="glass p-5 text-sm text-zinc-400">Loading runs...</div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="glass p-5 text-sm text-zinc-400">
        No runs yet. Instrument an agent to see it here.
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {runs.map((run) => (
        <li key={run.id}>
          <Link
            href={`/run/${run.id}`}
            className="glass group flex items-center justify-between gap-4 px-5 py-4 transition hover:border-white/15 hover:bg-white/[0.03]"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <code className="text-xs text-zinc-500">
                  {shortId(run.id)}
                </code>
                <span
                  className={`text-xs font-medium ${
                    STATUS_COLORS[run.status] ?? "text-zinc-400"
                  }`}
                >
                  {run.status === "running" && (
                    <span className="live-dot mr-1.5" />
                  )}
                  {run.status}
                </span>
              </div>
              <h3 className="mt-1 truncate text-base font-medium text-zinc-100">
                {run.goal ?? "(untitled run)"}
              </h3>
              <div className="mt-1 flex items-center gap-4 text-xs text-zinc-500">
                <span>{run.totalEvents} events</span>
                <span>{run.totalToolCalls} tools</span>
                {run.totalRetries > 0 && (
                  <span className="text-amber-400">
                    {run.totalRetries} retries
                  </span>
                )}
                {run.totalSubagents > 0 && (
                  <span>{run.totalSubagents} subagents</span>
                )}
                <span>{formatTimestamp(run.startedAt)}</span>
              </div>
            </div>
            <div className="hidden text-right text-xs text-zinc-500 sm:block">
              {run.completedAt && run.startedAt && (
                <div>{formatDuration(run.completedAt - run.startedAt)}</div>
              )}
              <div className="mt-1 text-zinc-600 transition group-hover:text-zinc-400">
                Open →
              </div>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
