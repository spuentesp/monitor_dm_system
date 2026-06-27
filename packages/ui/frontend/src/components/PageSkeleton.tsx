"use client";

import { cn } from "@/lib/utils";

export function PageSkeleton({
  variant = "default",
  rows = 4,
  className,
}: {
  variant?: "default" | "two-column" | "compact";
  rows?: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex-1 p-6 space-y-4 animate-pulse",
        variant === "two-column" && "grid grid-cols-1 lg:grid-cols-3 gap-6",
        className,
      )}
      aria-busy="true"
      aria-live="polite"
      role="status"
    >
      <div className="h-8 w-48 bg-white/5 rounded-lg" />
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "h-12 bg-white/[0.03] rounded-lg border border-white/5",
            variant === "two-column" && "lg:col-span-2",
          )}
          style={{ opacity: 1 - i * 0.12 }}
        />
      ))}
    </div>
  );
}
