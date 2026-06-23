"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

/**
 * Global "which world am I in" context (T-077 / plan T-056).
 *
 * One persisted selection shared by Play setup, the GM Assistant, and the
 * Worlds tree, so users stop re-finding their universe among walkthrough
 * debris on every page. URL params (?universe=) still win over this default
 * on pages that support deep links.
 */

export interface WorldSelection {
  multiverseId: string | null;
  universeId: string | null;
  universeLabel: string | null;
}

interface WorldContextValue extends WorldSelection {
  setWorld: (sel: WorldSelection) => void;
  clearWorld: () => void;
}

const STORAGE_KEY = "monitor.world-context.v1";

const WorldContext = createContext<WorldContextValue | undefined>(undefined);

function load(): WorldSelection {
  if (typeof window === "undefined") {
    return { multiverseId: null, universeId: null, universeLabel: null };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<WorldSelection>;
      return {
        multiverseId: parsed.multiverseId ?? null,
        universeId: parsed.universeId ?? null,
        universeLabel: parsed.universeLabel ?? null,
      };
    }
  } catch {
    // corrupted storage — fall through to empty
  }
  return { multiverseId: null, universeId: null, universeLabel: null };
}

export function WorldContextProvider({ children }: { children: ReactNode }) {
  // Start empty on both server and client to keep hydration consistent;
  // hydrate from localStorage after mount.
  const [sel, setSel] = useState<WorldSelection>({
    multiverseId: null,
    universeId: null,
    universeLabel: null,
  });

  useEffect(() => {
    setSel(load());
  }, []);

  const setWorld = useCallback((next: WorldSelection) => {
    setSel(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // storage full/blocked — selection still works for this tab
    }
  }, []);

  const clearWorld = useCallback(() => {
    setWorld({ multiverseId: null, universeId: null, universeLabel: null });
  }, [setWorld]);

  return (
    <WorldContext.Provider value={{ ...sel, setWorld, clearWorld }}>
      {children}
    </WorldContext.Provider>
  );
}

export function useWorldContext(): WorldContextValue {
  const ctx = useContext(WorldContext);
  if (!ctx) throw new Error("useWorldContext must be used within WorldContextProvider");
  return ctx;
}
