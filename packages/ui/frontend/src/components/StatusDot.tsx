import { cn, statusDotClass } from "@/lib/utils";

interface StatusDotProps {
  status: string;
  animate?: boolean;
  className?: string;
}

export function StatusDot({ status, animate = true, className }: StatusDotProps) {
  return (
    <span className="relative inline-flex h-2 w-2 flex-shrink-0">
      {animate && (status === "online" || status === "connected") && (
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping",
            "bg-emerald-400",
          )}
        />
      )}
      <span
        className={cn(
          "relative inline-flex rounded-full h-2 w-2",
          statusDotClass(status),
          className,
        )}
      />
    </span>
  );
}
