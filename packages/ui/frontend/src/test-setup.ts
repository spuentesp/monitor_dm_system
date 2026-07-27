// Vitest setup — runs before each test file.
// Registers @testing-library/jest-dom matchers (toBeInTheDocument, etc.)
// so component tests can use the standard accessible queries.
//
// Also wires automatic cleanup for @testing-library/react so renders from
// previous tests don't leak into the next (which otherwise causes
// "multiple elements with role" errors when querying by accessible name).
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});