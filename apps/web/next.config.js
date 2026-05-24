/**
 * Next.js config.
 *
 * Two modes are supported via the ``REVERIE_BUILD_MODE`` env var:
 *
 *   - **dev / default**: standard Next dev or build, with rewrites that proxy
 *     ``/api/v1/*`` and ``/health`` to a separate FastAPI backend (so the dev
 *     server can talk to it without CORS).
 *
 *   - **static** (``REVERIE_BUILD_MODE=static``): produces a fully static
 *     export under ``out/`` that the FastAPI backend serves directly. No
 *     rewrites — relative paths land on the same origin so ``/api/v1/*`` is
 *     served by the same uvicorn process.
 *
 * The static-export build is what makes ``pipx install reverie`` and
 * ``reverie start`` "just work" without users needing Node + pnpm.
 */

const isStatic = process.env.REVERIE_BUILD_MODE === "static";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Three.js + R3F-related deps benefit from package transpilation in Next.
  transpilePackages: [
    "three",
    "three-stdlib",
    "@react-three/fiber",
    "@react-three/drei",
    "@react-three/postprocessing",
    "@reverie/schema",
  ],

  // Static export: emit ``out/`` as a fully self-contained, server-less
  // bundle. ``trailingSlash: true`` + ``unoptimized`` images are required
  // because there's no Next runtime to handle redirects or image
  // optimisation when served from FastAPI.
  ...(isStatic
    ? {
        output: "export",
        trailingSlash: true,
        images: { unoptimized: true },
      }
    : {
        async rewrites() {
          const backend =
            process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";
          return [
            { source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
            { source: "/health", destination: `${backend}/health` },
          ];
        },
      }),
};

export default nextConfig;
