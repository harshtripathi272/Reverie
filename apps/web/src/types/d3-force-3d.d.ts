/**
 * Ambient types for `d3-force-3d`.
 *
 * The package itself doesn't ship its own types and there's no
 * `@types/d3-force-3d` on npm, so we declare the slice we use. Updating this
 * is fine; it's a frontend-only file and tracks our actual usage.
 */

declare module "d3-force-3d" {
  export interface SimulationNode {
    index?: number;
    x?: number;
    y?: number;
    z?: number;
    vx?: number;
    vy?: number;
    vz?: number;
    fx?: number | null;
    fy?: number | null;
    fz?: number | null;
  }

  export interface SimulationLink<N extends SimulationNode = SimulationNode> {
    source: string | number | N;
    target: string | number | N;
    index?: number;
  }

  export interface Force<N extends SimulationNode = SimulationNode> {
    (alpha: number): void;
    initialize?(nodes: N[], random: () => number): void;
    [option: string]: unknown;
  }

  export interface Simulation<N extends SimulationNode = SimulationNode> {
    nodes(): N[];
    nodes(nodes: N[]): this;
    alpha(): number;
    alpha(alpha: number): this;
    alphaMin(alpha: number): this;
    alphaDecay(alpha: number): this;
    alphaTarget(target: number): this;
    velocityDecay(decay: number): this;
    force<F extends Force<N>>(name: string, force?: F | null): this;
    on(typenames: string, listener?: (this: this) => void): this;
    tick(iterations?: number): this;
    stop(): this;
    restart(): this;
    numDimensions(n: number): this;
  }

  export function forceSimulation<N extends SimulationNode = SimulationNode>(
    nodes?: N[],
    numDimensions?: number,
  ): Simulation<N>;

  export function forceManyBody<N extends SimulationNode = SimulationNode>(): Force<N> & {
    strength(s: number | ((d: N) => number)): Force<N>;
    distanceMin(n: number): Force<N>;
    distanceMax(n: number): Force<N>;
  };

  export function forceCenter<N extends SimulationNode = SimulationNode>(
    x?: number,
    y?: number,
    z?: number,
  ): Force<N>;

  export function forceLink<
    N extends SimulationNode = SimulationNode,
    L extends SimulationLink<N> = SimulationLink<N>,
  >(links?: L[]): Force<N> & {
    id(accessor: (d: N) => string | number): ReturnType<typeof forceLink<N, L>>;
    links(links: L[]): ReturnType<typeof forceLink<N, L>>;
    distance(d: number | ((l: L) => number)): ReturnType<typeof forceLink<N, L>>;
    strength(s: number | ((l: L) => number)): ReturnType<typeof forceLink<N, L>>;
    iterations(n: number): ReturnType<typeof forceLink<N, L>>;
  };

  export function forceCollide<N extends SimulationNode = SimulationNode>(
    radius?: number | ((d: N) => number),
  ): Force<N> & {
    radius(r: number | ((d: N) => number)): Force<N>;
    iterations(n: number): Force<N>;
    strength(s: number): Force<N>;
  };

  export function forceX<N extends SimulationNode = SimulationNode>(
    x?: number | ((d: N) => number),
  ): Force<N> & { strength(s: number): Force<N> };

  export function forceY<N extends SimulationNode = SimulationNode>(
    y?: number | ((d: N) => number),
  ): Force<N> & { strength(s: number): Force<N> };

  export function forceZ<N extends SimulationNode = SimulationNode>(
    z?: number | ((d: N) => number),
  ): Force<N> & { strength(s: number): Force<N> };
}
