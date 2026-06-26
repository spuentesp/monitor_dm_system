import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  esbuild: {
    // Use the automatic JSX runtime so component tests don't need
    // `import React from "react"` at the top of every file.
    jsx: "automatic",
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["./src/test-setup.ts"],
    // React hook / component tests opt in via `// @vitest-environment happy-dom`
    // at the top of the file. Pure-logic tests in src/lib stay on node.
  },
});