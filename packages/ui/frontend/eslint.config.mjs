import nextPlugin from "eslint-config-next";

export default [
  ...nextPlugin,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "src/**/*.test.ts",
      "src/**/*.test.tsx",
      "src/**/__dbg__*",
    ],
  },
];
