/**
 * Thin API client for the Reverie backend.
 *
 * Uses Next.js's rewrites (see next.config.js) so the same code works both
 * when the dev server proxies to localhost:8000 and when it's served from a
 * single origin in production.
 */

import type { GraphBundle, Run, RunPage } from "@/lib/types";

const BASE = "/api/v1";

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(path, {
    headers: { accept: "application/json" },
    cache: "no-store",
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new ApiError(resp.status, `${resp.status} ${path}: ${text}`);
  }
  return (await resp.json()) as T;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const resp = await fetch(path, {
    method: "POST",
    headers: { accept: "application/json", "content-type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new ApiError(resp.status, `${resp.status} ${path}: ${text}`);
  }
  return (await resp.json()) as T;
}

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// Endpoints used by the frontend
// ---------------------------------------------------------------------------

export async function listRuns(opts?: { limit?: number }): Promise<RunPage> {
  const limit = opts?.limit ?? 50;
  return get<RunPage>(`${BASE}/runs?limit=${limit}&offset=0`);
}

export async function getRun(runId: string): Promise<Run> {
  return get<Run>(`${BASE}/runs/${runId}`);
}

export async function getGraph(
  runId: string,
  opts?: { level?: 1 | 2 | 3 | 4 },
): Promise<GraphBundle> {
  const q = opts?.level !== undefined ? `?level=${opts.level}` : "";
  return get<GraphBundle>(`${BASE}/runs/${runId}/graph${q}`);
}

export async function getSalienceGraph(
  runId: string,
  opts?: { level?: 1 | 2 | 3 | 4; hideNoise?: boolean },
): Promise<GraphBundle> {
  const params = new URLSearchParams();
  if (opts?.level !== undefined) params.set("level", String(opts.level));
  if (opts?.hideNoise) params.set("hide_noise", "true");
  const q = params.toString() ? `?${params}` : "";
  return get<GraphBundle>(`${BASE}/runs/${runId}/salience${q}`);
}

export async function getClusterSummary(
  runId: string,
  clusterId: string,
  opts?: { refresh?: boolean },
): Promise<{
  runId: string;
  clusterId: string;
  memberCount: number;
  summary: string;
  status: string;
  model: string;
  detail: string;
}> {
  const q = opts?.refresh ? "?refresh=true" : "";
  return post(`${BASE}/runs/${runId}/clusters/${clusterId}/summary${q}`);
}

// ---------------------------------------------------------------------------
// Event details (full payload for rich rendering in the detail panel)
// ---------------------------------------------------------------------------

export interface FullEvent {
  id: string;
  type: string;
  runId: string;
  sessionId: string;
  agentId: string;
  parentId: string | null;
  depth: number;
  timestamp: number;
  durationMs: number | null;
  payload: Record<string, unknown>;
  salience: number | null;
  anomaly: boolean;
  schemaVersion: string;
}

/** Fetches every event for a run. Used to look up payloads by node id. */
export async function getRunEvents(runId: string): Promise<FullEvent[]> {
  return get<FullEvent[]>(`${BASE}/runs/${runId}/events`);
}

// ---------------------------------------------------------------------------
// Annotations — user-supplied feedback on nodes
// ---------------------------------------------------------------------------

export type AnnotationKind = "avoid" | "focus" | "done" | "note";
export type AnnotationScope = "agent" | "run";

export interface Annotation {
  id: string;
  runId: string;
  nodeId: string;
  kind: AnnotationKind;
  note: string | null;
  scope: AnnotationScope;
  agentId: string;
  tag: string | null;
  createdAt: number;
}

export interface AnnotationListResponse {
  items: Annotation[];
}

export async function listAnnotations(
  runId: string,
): Promise<AnnotationListResponse> {
  return get<AnnotationListResponse>(`${BASE}/runs/${runId}/annotations`);
}

export async function createAnnotation(
  runId: string,
  body: {
    nodeId: string;
    kind: AnnotationKind;
    note?: string;
    scope?: AnnotationScope;
    tag?: string;
  },
): Promise<Annotation> {
  return post<Annotation>(`${BASE}/runs/${runId}/annotations`, body);
}

export async function createAnnotationsBatch(
  runId: string,
  items: Array<{
    nodeId: string;
    kind: AnnotationKind;
    note?: string;
    scope?: AnnotationScope;
    tag?: string;
  }>,
): Promise<AnnotationListResponse> {
  return post<AnnotationListResponse>(`${BASE}/runs/${runId}/annotations`, {
    items,
  });
}

export async function deleteAnnotation(
  annotationId: string,
): Promise<{ ok: boolean; deleted: number }> {
  const resp = await fetch(`${BASE}/annotations/${annotationId}`, {
    method: "DELETE",
    headers: { accept: "application/json" },
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new ApiError(resp.status, text);
  }
  return (await resp.json()) as { ok: boolean; deleted: number };
}

export async function deleteRunAnnotations(
  runId: string,
): Promise<{ ok: boolean; deleted: number }> {
  const resp = await fetch(`${BASE}/runs/${runId}/annotations`, {
    method: "DELETE",
    headers: { accept: "application/json" },
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new ApiError(resp.status, text);
  }
  return (await resp.json()) as { ok: boolean; deleted: number };
}
