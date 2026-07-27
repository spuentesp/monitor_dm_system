import { Suspense } from "react";
import { ErrorBoundary } from "react-error-boundary";

export function QueryBoundary({ children, fallback }: { children: React.ReactNode; fallback?: React.ReactNode }) {
  return (
    <ErrorBoundary fallbackRender={({ error }) => (
      <div className="text-red-500">
        Error: {error instanceof Error ? error.message : String(error)}
      </div>
    )}>
      <Suspense fallback={fallback || <div>Loading...</div>}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}
