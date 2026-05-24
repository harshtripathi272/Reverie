"use client";

/**
 * Run explorer page (query-string variant).
 *
 * Static-export rule: every Next.js route must be reachable without
 * server-side runtime. Run IDs are unbounded, so a path-segment dynamic
 * route (``/run/[id]``) requires either SSR or pre-rendering every run at
 * build time. Neither works for our use case (the backend is the source
 * of truth, not the build).
 *
 * Solution: read the run id from the query string (``/run?id=...``).
 * The URL stays stable, the runs-list links to ``/run?id=<id>``, and the
 * page becomes a fully static, client-only SPA route.
 */

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Explorer } from "@/components/explorer/explorer";
import { Header } from "@/components/hud/header";
import { LoadingOverlay } from "@/components/hud/loading-overlay";

function RunPageInner() {
  const searchParams = useSearchParams();
  // ``useSearchParams`` returns null during the very first render in some
  // edge cases — bind the value to local state so the initial paint is
  // deterministic.
  const [runId, setRunId] = useState<string | null>(null);

  useEffect(() => {
    setRunId(searchParams.get("id"));
  }, [searchParams]);

  if (runId === null) {
    // First render or no `id=` provided.
    return (
      <div className="flex h-screen w-screen flex-col bg-black">
        <Header />
        <main className="flex flex-1 items-center justify-center px-6 text-zinc-400">
          <div className="max-w-md text-center text-sm">
            <p className="font-medium text-zinc-200">No run selected.</p>
            <p className="mt-2">
              Pick a run from the home page, or pass{" "}
              <code className="rounded bg-white/5 px-1.5 py-0.5 text-zinc-300">
                ?id=&lt;run-id&gt;
              </code>{" "}
              in the URL.
            </p>
          </div>
        </main>
      </div>
    );
  }

  return <Explorer runId={runId} />;
}

export default function RunPage() {
  return (
    <Suspense fallback={<LoadingOverlay message="Loading..." />}>
      <RunPageInner />
    </Suspense>
  );
}
