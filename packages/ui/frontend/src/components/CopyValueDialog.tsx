"use client";

import { useState } from "react";
import type { ElementType } from "react";
import { Check, Copy } from "lucide-react";
import { DialogShell, DialogFooter } from "@/components/DialogShell";

/**
 * One-time secret display: shows `value` in a selectable field with a copy
 * button. Used for admin reset links, invite links and fresh API tokens —
 * anywhere the value is only available at creation time.
 */
export function CopyValueDialog({
  title,
  icon,
  label,
  value,
  hint,
  onClose,
}: {
  title: string;
  icon: ElementType;
  label: string;
  value: string;
  hint?: string;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard unavailable (permissions/insecure context) — the input is
      // selectable so the user can copy manually.
    }
  };

  return (
    <DialogShell title={title} icon={icon} onClose={onClose} maxWidthClassName="max-w-lg">
      <div className="p-4 space-y-3">
        <p className="text-xs text-slate-400">{label}</p>
        <div className="flex gap-2">
          <input
            readOnly
            aria-label={label}
            value={value}
            onFocus={(e) => e.currentTarget.select()}
            className="input-cyber flex-1 text-xs font-mono"
          />
          <button type="button" onClick={copy} className="btn-ghost text-xs gap-1.5" aria-label="Copy">
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        {hint && <p className="text-[11px] text-slate-500">{hint}</p>}
      </div>
      <DialogFooter>
        <button type="button" className="btn-cyber text-xs" onClick={onClose}>
          Done
        </button>
      </DialogFooter>
    </DialogShell>
  );
}
