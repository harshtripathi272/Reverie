/**
 * Wire-format types as used by the frontend.
 *
 * These are deliberately *narrower* than the canonical types in
 * `@reverie/schema` — the renderer only needs a small slice. Re-deriving here
 * also avoids pulling Zod into the client bundle.
 */

export type ZoomLevel = 1 | 2 | 3 | 4;

export type RunStatus = "running" | "completed" | "failed" | "aborted";

export interface Run {
  id: string;
  sessionId: string;
  agentId: string;
  runtime: string;
  startedAt: number;
  completedAt: number | null;
  status: RunStatus;
  goal: string | null;
  totalEvents: number;
  totalTokens: number;
  totalToolCalls: number;
  totalRetries: number;
  totalSubagents: number;
  pinned: boolean;
  tags: string[];
  createdAt: number;
}

export interface RunPage {
  items: Run[];
  total: number;
  limit: number;
  offset: number;
}

export type AnomalyKind =
  | "loop"
  | "hotspot"
  | "bottleneck"
  | "poison"
  | "explosion"
  | "abandon";

export interface AnomalyAnnotation {
  kind: AnomalyKind;
  severity: "info" | "warning" | "error";
  detail: string;
}

export interface ClusterRef {
  clusterId: string;
  role: "root" | "member";
}

export interface GraphNode {
  id: string;
  type: string;
  parentId: string | null;
  depth: number;
  timestamp: number;
  durationMs: number | null;
  salience: number | null;
  anomaly: boolean;
  zoomLevel: ZoomLevel;
  anomalies: AnomalyAnnotation[];
  cluster: ClusterRef | null;
  onCriticalPath: boolean;
  label: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  onCriticalPath: boolean;
}

export interface GraphCluster {
  id: string;
  label: string;
  rootEventId: string | null;
  memberEventIds: string[];
  type: "goal" | "subagent" | "tool_storm" | "structural";
}

export interface GraphSummary {
  totalNodes: number;
  totalEdges: number;
  nodesPerZoom: Record<string, number>;
  anomaliesByKind: Record<string, number>;
  criticalPathLength: number;
}

export interface GraphBundle {
  runId: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters: GraphCluster[];
  criticalPath: string[];
  summary: GraphSummary;
}
