import Link from "next/link";
import { RunsList } from "@/components/runs/runs-list";
import { Header } from "@/components/hud/header";

export default function HomePage() {
  return (
    <div className="flex h-screen w-screen flex-col bg-black">
      <Header />
      <main className="flex flex-1 items-start justify-center overflow-y-auto px-6 py-12">
        <div className="w-full max-w-3xl">
          <div className="mb-10 animate-fade-in">
            <h1 className="text-4xl font-semibold tracking-tight text-zinc-100">
              Cognitive observability
            </h1>
            <p className="mt-3 max-w-xl text-zinc-400">
              Pick a run to explore its cognitive topology in three dimensions.
              Each orb is a thought; each filament is a causal link.
            </p>
            <p className="mt-3 text-xs text-zinc-500">
              No runs yet?{" "}
              <code className="rounded bg-white/5 px-1.5 py-0.5 text-zinc-300">
                reverie run python examples/complex_agent.py
              </code>
            </p>
          </div>
          <RunsList />
        </div>
      </main>
    </div>
  );
}
