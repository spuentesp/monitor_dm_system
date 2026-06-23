import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    middlewareClientMaxBodySize: "200mb",
  },
  // NOTE: no rewrites() here on purpose. /api/* is proxied by the runtime
  // route handler at src/app/api/[...path]/route.ts, which reads BACKEND_URL
  // at request time. A build-time rewrite would bake NEXT_PUBLIC_API_URL
  // (browser-facing, e.g. localhost:8001) into the server bundle and shadow
  // the handler with a wrong-at-runtime upstream (T-072).
};

export default nextConfig;
