"use client";

import type { ElementType, ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { DialogShell, DialogFooter } from "@/components/DialogShell";
import { cn } from "@/lib/utils";

/**
 * Shared confirmation dialog (DialogShell-based) for destructive or
 * account-level admin actions: ban, role change, session revocation.
 * Optional `children` render extra inputs (e.g. a ban reason).
 */
export function ConfirmDialog({
  title,
  icon,
  message,
  children,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: {
  title: string;
  icon: ElementType;
  message: ReactNode;
  children?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <DialogShell title={title} icon={icon} onClose={onClose}>
      <div className="p-4 space-y-3">
        <p className="text-sm text-slate-300">{message}</p>
        {children}
      </div>
      <DialogFooter>
        <button type="button" className="btn-ghost text-xs" onClick={onClose} disabled={busy}>
          {cancelLabel}
        </button>
        <button
          type="button"
          className={cn("text-xs gap-1.5", danger ? "btn-cyber text-red-200" : "btn-cyber")}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {confirmLabel}
        </button>
      </DialogFooter>
    </DialogShell>
  );
}
