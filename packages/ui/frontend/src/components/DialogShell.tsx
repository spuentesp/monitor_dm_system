"use client";

import { useEffect, type ElementType, type ReactNode } from "react";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

type DialogShellProps = {
  title: string;
  icon: ElementType;
  iconClassName?: string;
  onClose: () => void;
  maxWidthClassName?: string;
  children: ReactNode;
  footer?: ReactNode;
};

export function DialogShell({
  title,
  icon: Icon,
  iconClassName,
  onClose,
  maxWidthClassName = "max-w-md",
  children,
  footer,
}: DialogShellProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div role="presentation" className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        className={cn(
          "relative z-10 w-full rounded-xl border border-border bg-bg-card shadow-2xl",
          maxWidthClassName,
        )}
      >
        <div className="flex items-center gap-3 border-b border-border p-4">
          <Icon className={cn("h-4 w-4 text-accent-primary", iconClassName)} />
          <h2 id="dialog-title" className="text-sm font-semibold text-fg-primary">{title}</h2>
          <button className="ml-auto btn-ghost p-1" onClick={onClose} title="Close dialog">
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
        {footer}
      </motion.div>
    </div>
  );
}

export function DialogFooter({ children }: { children: ReactNode }) {
  return <div className="flex justify-end gap-2 border-t border-border p-4">{children}</div>;
}
