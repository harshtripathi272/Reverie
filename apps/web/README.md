# @reverie/web — 3D spatial renderer

The frontend for Reverie. A Next.js 15 app that renders agent runs as a
glowing orb world via Three.js + React Three Fiber.

## Quick start

In one terminal, start the backend:

```
.venv/Scripts/python.exe -m reverie_api
```

In a second terminal, run an instrumented agent so there's data to see:

```
reverie run python examples/complex_agent.py
```

In a third terminal, start the web app:

```
pnpm install              # once
pnpm -C apps/web dev      # http://localhost:3000
```

Open `http://localhost:3000` and click any run to enter its 3D explorer.

## Visual stack

- **Three.js + React Three Fiber 9** for the scene graph.
- **postprocessing v6** for the bloom + ACES tone-mapping pipeline.
- **`d3-force-3d`** for the layout simulation; goal nodes are pinned along
  a vertical depth axis and everything else orbits around them.
- **Custom Fresnel shader** on each orb so the glow is rim-focused rather
  than a flat halo, giving each node a "bioluminescent" feel.
- **Tailwind CSS** with glass-morphism utility classes for HUD panels.
- **Zustand** for ephemeral UI state (selection, zoom, noise filter).

## Layout

```
src/
├── app/                 — Next.js routes (`/`, `/run/[id]`)
├── components/
│   ├── explorer/        — Top-level run explorer wiring data → scene
│   ├── scene/           — Three.js components (orbs, edges, starfield)
│   └── hud/             — Glassmorphism overlay (zoom, stats, detail)
├── lib/                 — API client, types, layout, colors, store
└── types/               — Ambient type declarations (d3-force-3d)
```

## Configuration

| Var | Default | Used in |
|---|---|---|
| `NEXT_PUBLIC_BACKEND_URL` | `http://127.0.0.1:8000` | dev server rewrites |

## Build

```
pnpm -C apps/web build
pnpm -C apps/web start
```

The optimized `/run/[id]` route lands at ~336 kB JS / ~442 kB First Load —
heavier than a typical CRUD UI but expected for a Three.js app.
