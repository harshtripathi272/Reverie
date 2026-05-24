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
