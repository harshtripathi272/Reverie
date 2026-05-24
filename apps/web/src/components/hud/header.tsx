"use client";

import Link from "next/link";

interface HeaderProps {
  /** Optional middle slot for run-specific HUD widgets. */
  middle?: React.ReactNode;
  /** Optional right slot. */
  right?: React.ReactNode;
}

export function Header({ middle, right }: HeaderProps) {
  return (
    <header className="relative z-30 flex items-center justify-between border-b border-white/5 bg-black/60 px-6 py-3 backdrop-blur-glass">
      <Link
        href="/"
        className="flex items-center gap-2 text-sm font-semibold tracking-wide text-zinc-200 hover:text-white"
      >
        <span className="text-glow-violet">◯</span>
        <span>Reverie</span>
      </Link>
      <div className="flex-1 px-6">
        <div className="mx-auto max-w-2xl">{middle}</div>
      </div>
      <div className="flex items-center gap-3 text-xs text-zinc-500">
        {right}
      </div>
    </header>
  );
}
