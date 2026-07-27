"use client";

import { AlertCircle, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";

export function PageError({
  title = "Something went wrong",
  detail,
  className,
}: {
  title?: string;
  detail?: string;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("flex-1 flex items-center justify-center p-8", className)}>
      <div className="max-w-md w-full glass rounded-2xl border border-red-500/20 p-6 space-y-4 text-center">
        <div className="flex justify-center">
          <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
            <AlertCircle className="w-6 h-6 text-red-400" />
          </div>
        </div>
        <div>
          <h2 className="text-base font-semibold text-slate-100">{title}</h2>
          {detail && (
            <p className="mt-1 text-xs text-slate-400 leading-relaxed break-words">{detail}</p>
          )}
        </div>
        <button
          onClick={() => window.location.reload()}
          className="btn-cyber inline-flex items-center gap-2 text-xs"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Reload
        </button>
      </div>
    </div>
  );
}
