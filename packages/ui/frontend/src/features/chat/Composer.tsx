"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatStatus } from "./types";
import { StatusPill } from "./StatusPill";

export interface QuickAction {
  /** Button label. */
  label: string;
  /** Optional icon component. */
  icon?: LucideIcon;
  /** Either fill the textarea and focus, OR submit immediately when clicked. */
  onClick: "fill" | "submit";
  /** The text to fill or submit. */
  text: string;
  /** When `fill`, focuses the textarea after placing text. Default true. */
  focus?: boolean;
  /** Optional title (tooltip). */
  title?: string;
  /** Tailwind class overrides for the button. */
  className?: string;
  /** Optional disabled condition — defaults to `isTyping`. */
  disabled?: boolean;
}

export interface ComposerProps {
  /** Current text in the textarea. */
  value: string;
  /** Called on every keystroke. */
  onChange: (v: string) => void;
  /** Called when the user submits (Enter). */
  onSubmit: (text: string) => void;
  /** Current WS status — controls the status pill. */
  status: ChatStatus;
  /** True while waiting for the GM's response. Disables Send. */
  isTyping?: boolean;
  /** Placeholder text. */
  placeholder?: string;
  /** Optional manual-retry callback (Disconnected state). */
  onReconnect?: () => void;
  /** Quick-action chips shown above the input. */
  quickActions?: QuickAction[];
  /** Render extra UI above the chips (e.g. benchmark probes). */
  extraTop?: React.ReactNode;
  /** Disable input + send button entirely. */
  disabled?: boolean;
  /** Visible label for the typing indicator (e.g. "GM is typing…"). */
  typingLabel?: string;
}

export function Composer({
  value,
  onChange,
  onSubmit,
  status,
  isTyping = false,
  placeholder,
  onReconnect,
  quickActions,
  extraTop,
  disabled = false,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const handleSend = useCallback(() => {
    const text = value.trim();
    if (!text || isTyping || disabled) return;
    onSubmit(text);
    onChange("");
    textareaRef.current?.focus();
  }, [value, isTyping, disabled, onSubmit, onChange]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleAction = (action: QuickAction) => {
    if (action.disabled || isTyping || disabled) return;
    if (action.onClick === "fill") {
      onChange(action.text);
      if (action.focus !== false) {
        // wait for state update to render before focusing
        requestAnimationFrame(() => textareaRef.current?.focus());
      }
    } else {
      onSubmit(action.text);
    }
  };

  // Keep the textarea focused when the user is idle, but yield when the
  // GM is typing so the user can read the bubble instead of having focus
  // yanked into a (potentially empty) input.
  useEffect(() => {
    if (!isTyping && textareaRef.current && document.activeElement === document.body) {
      textareaRef.current.focus();
    }
  }, [isTyping]);

  const canSend = value.trim().length > 0 && !isTyping && !disabled;

  return (
    <div className="px-6 pb-5 pt-3 border-t border-white/5">
      {extraTop}
      {quickActions && quickActions.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {quickActions.map((action, i) => (
            <button
              key={`${action.label}-${i}`}
              onClick={() => handleAction(action)}
              disabled={action.disabled ?? isTyping}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border border-white/10 text-slate-400 hover:text-slate-100 hover:border-cyan-500/30 hover:bg-cyan-500/10 disabled:opacity-40 transition-all",
                action.className,
              )}
              title={action.title}
            >
              {action.icon && <action.icon className="w-3 h-3" />}
              {action.label}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end gap-3 glass rounded-xl p-3">
        {status !== "connected" && (
          <div className="mb-auto">
            <StatusPill status={status} onRetry={onReconnect} />
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={2}
          disabled={disabled}
          className="flex-1 bg-transparent text-sm text-slate-200 placeholder:text-slate-600 resize-none focus:outline-none disabled:opacity-50"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Send message"
          className={cn(
            "flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150",
            canSend
              ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/25 hover:shadow-cyan-glow"
              : "bg-white/4 text-slate-600 border border-white/8 cursor-not-allowed",
          )}
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
      <p className="text-[10px] text-slate-700 mt-2 text-center">
        Enter to send · Shift + Enter for new line
      </p>
    </div>
  );
}