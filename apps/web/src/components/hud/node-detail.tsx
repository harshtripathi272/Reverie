"use client";

/**
 * Node detail panel — rich, payload-aware view of one selected event.
 *
 * The graph endpoint only ships a one-line ``label`` per node to keep the
 * payload small. The detail panel needs the *full* event (with the URL the
 * agent searched, the actual query string, the tool's response, the memory
 * content it pulled, etc.) — so we lazy-load all of the run's events the
 * first time someone clicks an orb and cache them in component state.
 */

import { useEffect, useMemo, useState } from "react";

import {
  createAnnotation,
  deleteAnnotation,
  getRunEvents,
  type Annotation,
  type AnnotationKind,
  type FullEvent,
} from "@/lib/api";
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
  const annotationsByNode = useExplorerStore((s) => s.annotationsByNode);
  const addAnnotations = useExplorerStore((s) => s.addAnnotations);
  const removeAnnotation = useExplorerStore((s) => s.removeAnnotation);

  // Cache full events for this run. Loaded on first selection.
  const [events, setEvents] = useState<Map<string, FullEvent> | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const runId = bundle.runId;

  useEffect(() => {
    if (events !== null || selectedNodeId == null) return;
    let cancelled = false;
    getRunEvents(runId)
      .then((list) => {
        if (cancelled) return;
        const map = new Map<string, FullEvent>();
        for (const e of list) map.set(e.id, e);
        setEvents(map);
      })
      .catch((e) => !cancelled && setEventsError(e?.message ?? String(e)));
    return () => {
      cancelled = true;
    };
  }, [runId, selectedNodeId, events]);

  if (selectedNodeId == null) return null;

  const node = bundle.nodes.find((n) => n.id === selectedNodeId);
  if (!node) return null;

  const fullEvent = events?.get(node.id) ?? null;
  const annotations = annotationsByNode.get(node.id) ?? [];

  const visual = visualFor(node.type);
  const salience = node.salience ?? 0;
  const sailbar = Math.max(0, Math.min(1, salience)) * 100;

  const onAnnotate = async (kind: AnnotationKind, note?: string) => {
    try {
      const created = await createAnnotation(runId, {
        nodeId: node.id,
        kind,
        note,
      });
      addAnnotations([created]);
    } catch (e) {
      console.error("annotate failed", e);
    }
  };

  const onRemoveAnnotation = async (annotationId: string) => {
    try {
      await deleteAnnotation(annotationId);
      removeAnnotation(annotationId);
    } catch (e) {
      console.error("delete annotation failed", e);
    }
  };

  return (
    <aside
      role="dialog"
      aria-label="Event detail"
      className="glass-strong w-[26rem] max-h-[calc(100vh-5rem)] overflow-y-auto animate-fade-in flex-col gap-3 p-4 text-sm"
    >
      <header className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 rounded-full shrink-0"
              style={{
                backgroundColor: visual.hex,
                boxShadow: `0 0 8px ${visual.hex}`,
              }}
            />
            <code className="font-mono text-xs text-zinc-300 truncate">
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

      {/* ----- Full payload (lazy-loaded from /events) ----- */}
      <PayloadView
        event={fullEvent}
        loading={events === null && !eventsError}
        error={eventsError}
      />

      {/* ----- Annotations on this node ----- */}
      {annotations.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs uppercase tracking-wider text-zinc-500">
            Your annotations
          </div>
          {annotations.map((a) => (
            <AnnotationRow
              key={a.id}
              annotation={a}
              onRemove={() => onRemoveAnnotation(a.id)}
            />
          ))}
        </div>
      )}

      {/* ----- Quick-action buttons for annotating ----- */}
      <div className="space-y-1.5">
        <div className="text-xs uppercase tracking-wider text-zinc-500">
          Steer next run
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <ActionButton
            kind="avoid"
            label="Avoid"
            color="rose"
            onClick={() => onAnnotate("avoid")}
          />
          <ActionButton
            kind="focus"
            label="Focus"
            color="amber"
            onClick={() => onAnnotate("focus")}
          />
          <ActionButton
            kind="done"
            label="Done"
            color="emerald"
            onClick={() => onAnnotate("done")}
          />
          <ActionButton
            kind="note"
            label="Note"
            color="sky"
            onClick={() => {
              const note = window.prompt(
                "Add a note (visible to the next run):",
              );
              if (note && note.trim()) onAnnotate("note", note.trim());
            }}
          />
        </div>
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

function PayloadView({
  event,
  loading,
  error,
}: {
  event: FullEvent | null;
  loading: boolean;
  error: string | null;
}) {
  if (error) {
    return (
      <div className="rounded-md border border-rose-400/30 bg-rose-500/10 px-2.5 py-1.5 text-xs text-rose-200">
        Could not load event details: {error}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="text-xs text-zinc-500 italic">
        Loading event details...
      </div>
    );
  }
  if (!event) return null;

  const payload = event.payload as Record<string, unknown>;
  const fields = formatPayloadFields(payload);

  return (
    <div className="space-y-1.5">
      <div className="text-xs uppercase tracking-wider text-zinc-500">
        Event content
      </div>
      <div className="space-y-1 rounded-md border border-white/5 bg-white/[0.02] p-2.5 text-xs">
        {fields.map(({ key, value, isLong }) => (
          <PayloadField
            key={key}
            label={key}
            value={value}
            isLong={isLong}
          />
        ))}
      </div>
    </div>
  );
}

interface FormattedField {
  key: string;
  value: string;
  isLong: boolean;
}

/**
 * Walk the payload object and produce a flat list of human-friendly
 * (label, value) pairs. Recurses one level into nested objects so e.g.
 * tool args show up as ``args.query: "AI agents"`` rather than just
 * ``args: {object}``.
 */
function formatPayloadFields(
  payload: Record<string, unknown>,
  prefix = "",
): FormattedField[] {
  const out: FormattedField[] = [];
  for (const [key, value] of Object.entries(payload)) {
    const labelKey = prefix ? `${prefix}.${key}` : key;
    // Skip the discriminator field — we already show the type at the top.
    if (key === "_type" || key === "kind") continue;
    if (value === null || value === undefined) continue;
    if (value === "") continue;

    if (typeof value === "object" && !Array.isArray(value)) {
      // Recurse one level for things like ``args``, ``result``.
      const nested = formatPayloadFields(
        value as Record<string, unknown>,
        labelKey,
      );
      out.push(...nested);
      continue;
    }

    let str: string;
    if (typeof value === "string") {
      str = value;
    } else if (Array.isArray(value)) {
      str = JSON.stringify(value);
    } else {
      str = String(value);
    }
    out.push({ key: labelKey, value: str, isLong: str.length > 60 });
  }
  return out;
}

function PayloadField({
  label,
  value,
  isLong,
}: {
  label: string;
  value: string;
  isLong: boolean;
}) {
  // Detect URLs — link them so the user can open the actual page the agent
  // searched / fetched.
  const isUrl = /^https?:\/\//.test(value);

  if (isLong) {
    return (
      <div>
        <div className="text-zinc-500 mb-0.5">{label}</div>
        {isUrl ? (
          <a
            href={value}
            target="_blank"
            rel="noopener noreferrer"
            className="block break-all rounded bg-black/30 px-2 py-1 font-mono text-[11px] text-cyan-300 hover:underline"
          >
            {value}
          </a>
        ) : (
          <pre className="whitespace-pre-wrap break-all rounded bg-black/30 px-2 py-1 font-mono text-[11px] text-zinc-200">
            {value}
          </pre>
        )}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[6.5rem_1fr] gap-2">
      <span className="text-zinc-500 truncate" title={label}>
        {label}
      </span>
      {isUrl ? (
        <a
          href={value}
          target="_blank"
          rel="noopener noreferrer"
          className="truncate font-mono text-[11px] text-cyan-300 hover:underline"
          title={value}
        >
          {value}
        </a>
      ) : (
        <span className="font-mono text-[11px] text-zinc-200 truncate" title={value}>
          {value}
        </span>
      )}
    </div>
  );
}

const KIND_STYLES: Record<
  AnnotationKind,
  { ring: string; bg: string; fg: string; symbol: string }
> = {
  avoid: {
    ring: "border-rose-400/40",
    bg: "bg-rose-500/10",
    fg: "text-rose-200",
    symbol: "✕",
  },
  focus: {
    ring: "border-amber-400/40",
    bg: "bg-amber-500/10",
    fg: "text-amber-200",
    symbol: "★",
  },
  done: {
    ring: "border-emerald-400/40",
    bg: "bg-emerald-500/10",
    fg: "text-emerald-200",
    symbol: "✓",
  },
  note: {
    ring: "border-sky-400/40",
    bg: "bg-sky-500/10",
    fg: "text-sky-200",
    symbol: "i",
  },
};

function AnnotationRow({
  annotation,
  onRemove,
}: {
  annotation: Annotation;
  onRemove: () => void;
}) {
  const styles = KIND_STYLES[annotation.kind];
  return (
    <div
      className={`flex items-center gap-2 rounded-md border ${styles.ring} ${styles.bg} px-2.5 py-1.5`}
    >
      <span className={`font-bold ${styles.fg}`}>{styles.symbol}</span>
      <div className="min-w-0 flex-1">
        <div className={`text-xs font-semibold uppercase ${styles.fg}`}>
          {annotation.kind}
        </div>
        {annotation.note && (
          <div className="text-xs text-zinc-300 break-words">
            {annotation.note}
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onRemove}
        className="rounded p-1 text-zinc-500 hover:bg-white/5 hover:text-zinc-200"
        aria-label="Remove annotation"
      >
        ×
      </button>
    </div>
  );
}

const COLOR_CLASSES: Record<
  string,
  { hover: string; ring: string; fg: string }
> = {
  rose: {
    hover: "hover:bg-rose-500/15 hover:border-rose-400/50",
    ring: "border-rose-400/30",
    fg: "text-rose-300",
  },
  amber: {
    hover: "hover:bg-amber-500/15 hover:border-amber-400/50",
    ring: "border-amber-400/30",
    fg: "text-amber-300",
  },
  emerald: {
    hover: "hover:bg-emerald-500/15 hover:border-emerald-400/50",
    ring: "border-emerald-400/30",
    fg: "text-emerald-300",
  },
  sky: {
    hover: "hover:bg-sky-500/15 hover:border-sky-400/50",
    ring: "border-sky-400/30",
    fg: "text-sky-300",
  },
};

function ActionButton({
  kind,
  label,
  color,
  onClick,
}: {
  kind: AnnotationKind;
  label: string;
  color: keyof typeof COLOR_CLASSES;
  onClick: () => void;
}) {
  const c = COLOR_CLASSES[color];
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border ${c.ring} ${c.hover} bg-transparent px-2.5 py-1.5 text-xs font-medium ${c.fg} transition`}
      title={`Mark as ${label.toLowerCase()} for the next run`}
    >
      {label}
    </button>
  );
}
