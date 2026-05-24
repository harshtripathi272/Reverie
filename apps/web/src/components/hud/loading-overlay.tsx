"use client";

/**
 * Center-of-screen loading overlay. A single soft-glowing dot pulses while
 * the graph payload is in flight. Designed to feel like the orbs are
 * about to "materialize" into the scene rather than a generic spinner.
 */

interface LoadingOverlayProps {
  message?: string;
}

export function LoadingOverlay({
  message = "Loading…",
}: LoadingOverlayProps) {
  return (
    <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center">
      <div className="glass-strong flex items-center gap-3 px-5 py-3 text-sm text-zinc-300">
        <span className="loading-orb" aria-hidden />
        <span>{message}</span>
      </div>
      <style jsx>{`
        .loading-orb {
          position: relative;
          display: inline-block;
          width: 12px;
          height: 12px;
          border-radius: 9999px;
          background: #7c3aed;
          box-shadow:
            0 0 12px rgba(124, 58, 237, 0.7),
            0 0 24px rgba(124, 58, 237, 0.35);
          animation: loadingPulse 1.6s ease-in-out infinite;
        }
        @keyframes loadingPulse {
          0%, 100% {
            transform: scale(1);
            opacity: 1;
          }
          50% {
            transform: scale(1.4);
            opacity: 0.55;
          }
        }
      `}</style>
    </div>
  );
}
