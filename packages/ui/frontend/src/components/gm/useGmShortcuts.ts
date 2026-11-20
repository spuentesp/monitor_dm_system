"use client";

import { useEffect, useRef } from "react";

export interface GmShortcutHandlers {
  /** r — focus the dice roller. */
  onRoll?: () => void;
  /** n — start a new scratchpad note. */
  onNewNote?: () => void;
}

/**
 * Focus the first VISIBLE element matching the selector (layouts mount the
 * desktop and narrow instances of a panel side by side and show one via CSS).
 * Falls back to focusing the first match. Returns whether a visible match
 * was found — callers can switch the visible panel and retry.
 */
export function focusFirstVisible(selector: string): boolean {
  if (typeof document === "undefined") return false;
  const els = Array.from(document.querySelectorAll<HTMLElement>(selector));
  if (els.length === 0) return false;
  const visible = els.find((el) => el.offsetParent !== null || el.getClientRects().length > 0);
  (visible ?? els[0]).focus();
  return Boolean(visible);
}

/**
 * j/k — move the active marker through the page's entries
 * (`[data-gm-entry]` elements: dice history, recorder transcript, threads…).
 */
export function moveGmEntry(delta: -1 | 1): void {
  if (typeof document === "undefined") return;
  const entries = Array.from(document.querySelectorAll<HTMLElement>("[data-gm-entry]"));
  if (entries.length === 0) return;
  const current = entries.findIndex((el) => el.getAttribute("data-gm-entry-active") === "true");
  const next =
    current === -1
      ? delta === 1
        ? 0
        : entries.length - 1
      : Math.min(entries.length - 1, Math.max(0, current + delta));
  entries.forEach((el, i) => {
    if (i === next) {
      el.setAttribute("data-gm-entry-active", "true");
      el.setAttribute("aria-current", "true");
      el.scrollIntoView?.({ block: "nearest" });
    } else {
      el.removeAttribute("data-gm-entry-active");
      el.removeAttribute("aria-current");
    }
  });
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  );
}

/**
 * Table shortcuts: r = focus dice roller, n = new scratchpad note,
 * j/k = next/prev entry. Ignored while typing in any form field and while
 * holding ctrl/meta/alt.
 */
export function useGmShortcuts(handlers: GmShortcutHandlers): void {
  const handlersRef = useRef(handlers);
  useEffect(() => {
    handlersRef.current = handlers;
  });

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      if (isEditableTarget(e.target)) return;
      const key = e.key.toLowerCase();
      if (key === "r") {
        e.preventDefault();
        handlersRef.current.onRoll?.();
      } else if (key === "n") {
        e.preventDefault();
        handlersRef.current.onNewNote?.();
      } else if (key === "j") {
        e.preventDefault();
        moveGmEntry(1);
      } else if (key === "k") {
        e.preventDefault();
        moveGmEntry(-1);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}
