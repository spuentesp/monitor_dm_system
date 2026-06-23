"use client";

import { useEffect } from "react";

/**
 * Root-level error boundary. Catches errors in the root layout
 * that error.tsx cannot handle (since error.tsx is rendered inside the layout).
 *
 * See: https://nextjs.org/docs/app/building-your-application/routing/error-handling#global-error-handling
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[MONITOR] Root error:", error.message, error.digest);
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0, background: "#0f172a" }}>
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "2rem",
          }}
        >
          <div style={{ textAlign: "center", maxWidth: "28rem" }}>
            <h1 style={{ color: "#f1f5f9", fontSize: "1.25rem", marginBottom: "0.5rem" }}>
              MONITOR encountered a critical error
            </h1>
            <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              The application failed to load. Please try refreshing the page.
            </p>
            <button
              onClick={reset}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "0.5rem",
                background: "rgba(6,182,212,0.15)",
                color: "#22d3ee",
                border: "1px solid rgba(6,182,212,0.3)",
                cursor: "pointer",
                fontSize: "0.875rem",
              }}
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}