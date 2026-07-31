"use client";

import { useEffect, useRef } from "react";

/**
 * Dismiss-on-outside-interaction for popovers/menus.
 *
 * Returns a ref to attach to the popover container. While `active`, a
 * mousedown outside the container or an Escape keypress invokes `onDismiss`.
 * Listeners are only attached while `active` (pass the popover's open state).
 */
export function useDismissRef<T extends HTMLElement>(onDismiss: () => void, active = true) {
  const ref = useRef<T>(null);

  useEffect(() => {
    if (!active) return;
    function onMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onDismiss();
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onDismiss();
    }
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onDismiss, active]);

  return ref;
}
