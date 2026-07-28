import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    middlewareClientMaxBodySize: "200mb",
  },
  // F1-1: Worlds/Snapshots/Systems/Architect moved under the Forge route
  // group. Real 307s at the edge prevent the 1-second meta-refresh + skeleton
  // flash that server-component `redirect()` produces in streaming SSR.
  // Query strings are appended automatically by the framework.
  async redirects() {
    return [
      { source: "/worlds", destination: "/forge/worlds", permanent: false },
      { source: "/snapshots", destination: "/forge/snapshots", permanent: false },
      { source: "/systems", destination: "/forge/systems", permanent: false },
      { source: "/architect", destination: "/forge/architect", permanent: false },
      { source: "/universes", destination: "/forge/worlds", permanent: false },
    ];
  },
  // NOTE: no rewrites() here on purpose. /api/* is proxied by the runtime
  // route handler at src/app/api/[...path]/route.ts, which reads BACKEND_URL
  // at request time. A build-time rewrite would bake NEXT_PUBLIC_API_URL
  // (browser-facing, e.g. localhost:8001) into the server bundle and shadow
  // the handler with a wrong-at-runtime upstream (T-072).
};

export default nextConfig;
