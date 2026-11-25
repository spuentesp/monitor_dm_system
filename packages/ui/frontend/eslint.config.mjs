import { FlatCompat } from "@eslint/eslintrc";

// eslint-config-next 15 ships a legacy (eslintrc) config; loading it as a flat
// config directly trips @rushstack/eslint-patch ("Failed to patch ESLint").
// FlatCompat translates it into flat-config form.
const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

export default [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
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
