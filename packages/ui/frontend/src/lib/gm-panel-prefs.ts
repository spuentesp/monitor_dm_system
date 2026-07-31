"use client";

import { useCallback, useState } from "react";

const ORDER_KEY = "monitor.gm.panelOrder";
const HIDDEN_KEY = "monitor.gm.hiddenPanels";

export interface GmPanelPrefs {
  order: string[];
  hidden: string[];
}

function readIds(key: string): string[] {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function readPanelPrefs(): GmPanelPrefs {
  if (typeof window === "undefined") return { order: [], hidden: [] };
  return { order: readIds(ORDER_KEY), hidden: readIds(HIDDEN_KEY) };
}

export function writePanelPrefs(prefs: GmPanelPrefs): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ORDER_KEY, JSON.stringify(prefs.order));
  window.localStorage.setItem(HIDDEN_KEY, JSON.stringify(prefs.hidden));
}

/**
 * Apply stored prefs to a panel id list: drop hidden ids, honor stored order,
 * append panels the stored order doesn't know about (new panels appear).
 */
export function visibleOrderedPanels<T extends string>(ids: T[], prefs: GmPanelPrefs): T[] {
  const available = new Set(ids);
  const ordered: T[] = [];
  for (const id of prefs.order) {
    if (available.has(id as T) && !ordered.includes(id as T)) ordered.push(id as T);
  }
  for (const id of ids) {
    if (!ordered.includes(id)) ordered.push(id);
  }
  return ordered.filter((id) => !prefs.hidden.includes(id));
}

/** React binding: keeps prefs in state and persists every change. */
export function useGmPanelPrefs() {
  const [prefs, setPrefs] = useState<GmPanelPrefs>(() => readPanelPrefs());

  const update = useCallback((next: GmPanelPrefs) => {
    setPrefs(next);
    writePanelPrefs(next);
  }, []);

  const setOrder = useCallback((order: string[]) => update({ ...readPanelPrefs(), order }), [update]);

  const toggleHidden = useCallback(
    (id: string) => {
      const cur = readPanelPrefs();
      const hidden = cur.hidden.includes(id)
        ? cur.hidden.filter((h) => h !== id)
        : [...cur.hidden, id];
      update({ ...cur, hidden });
    },
    [update],
  );

  const move = useCallback(
    (id: string, dir: -1 | 1, ids: string[]) => {
      const cur = readPanelPrefs();
      const order = visibleOrderedPanels(ids, cur);
      const i = order.indexOf(id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= order.length) return;
      [order[i], order[j]] = [order[j], order[i]];
      update({ ...cur, order });
    },
    [update],
  );

  return { prefs, setOrder, toggleHidden, move };
}
