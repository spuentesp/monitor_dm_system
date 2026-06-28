"use client";

import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  Clapperboard,
  FileText,
  Loader2,
  Search,
  Sparkles,
  Users,
  WifiOff,
} from "lucide-react";
import Link from "next/link";
import { searchApi, universesApi } from "@/lib/api";
import type { SearchResultItem, Universe } from "@/lib/types";
import { cn, truncate } from "@/lib/utils";

const COLLECTIONS = [
  { id: "entities", label: "Entities", icon: Users },
  { id: "scenes", label: "Scenes", icon: Clapperboard },
  { id: "snippets", label: "Snippets", icon: FileText },
  { id: "knowledge", label: "Knowledge", icon: BookOpen },
] as const;

type CollectionId = (typeof COLLECTIONS)[number]["id"];

export default function SearchPage() {
  return (
    <Suspense fallback={null}>
      <SearchPageInner />
    </Suspense>
  );
}

function SearchPageInner() {
  const params = useSearchParams();
  const router = useRouter();
  const initialQ = params.get("q") ?? "";

  const [input, setInput] = useState(initialQ);
  const [query, setQuery] = useState(initialQ);
  const [universeId, setUniverseId] = useState<string>("");
  const [enabled, setEnabled] = useState<Set<CollectionId>>(
    () => new Set(COLLECTIONS.map((c) => c.id)),
  );

  const universesQ = useQuery({
    queryKey: ["universes"],
    queryFn: () => universesApi.listUniverses(),
  });

  const searchQ = useQuery({
    queryKey: ["semantic-search", query, universeId, [...enabled].sort().join(",")],
    queryFn: () =>
      searchApi.search(query, {
        universe_id: universeId || undefined,
        collections: [...enabled].join(","),
        limit: 20,
      }),
    enabled: query.trim().length > 0,
  });

  const submit = () => {
    const q = input.trim();
    if (!q) return;
    setQuery(q);
    router.replace(`/search?q=${encodeURIComponent(q)}`);
  };

  const toggle = (id: CollectionId) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        if (next.size > 1) next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ─── Header ──────────────────────────────────────── */}
      <div className="border-b border-zinc-800 px-6 py-4 space-y-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-cyan-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Semantic Search</h1>
          <span className="text-xs text-zinc-500">
            Q-1…Q-5 — entities, scenes, snippets & knowledge
          </span>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-2xl">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="Ask the canon — “who rules the Silver Alliance?”"
              aria-label="Search the canon"
              className="w-full bg-zinc-900 border border-zinc-700 rounded-lg pl-9 pr-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <button
            onClick={submit}
            disabled={!input.trim()}
            className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-sm font-medium text-white"
          >
            Search
          </button>
        </div>

        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-1.5">
            {COLLECTIONS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => toggle(id)}
                aria-pressed={enabled.has(id)}
                className={cn(
                  "flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border transition-colors",
                  enabled.has(id)
                    ? "bg-cyan-500/10 border-cyan-500/40 text-cyan-300"
                    : "bg-zinc-900 border-zinc-700 text-zinc-500 hover:text-zinc-300",
                )}
              >
                <Icon className="w-3 h-3" />
                {label}
              </button>
            ))}
          </div>

          <select
            value={universeId}
            onChange={(e) => setUniverseId(e.target.value)}
            className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-300"
          >
            <option value="">All universes</option>
            {(universesQ.data ?? []).map((u: Universe) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ─── Results ─────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {!query && (
          <div className="text-center text-zinc-600 mt-24 text-sm">
            Type a question or phrase to search the canon semantically.
          </div>
        )}

        {searchQ.isFetching && (
          <div className="flex items-center gap-2 text-zinc-400 text-sm mt-8">
            <Loader2 className="w-4 h-4 animate-spin" /> Embedding query &
            searching…
          </div>
        )}

        {searchQ.isError && (
          <div className="flex items-center gap-2 text-amber-400 text-sm mt-8">
            <WifiOff className="w-4 h-4" />
            Search failed — is the backend (and its embedding provider)
            reachable?
          </div>
        )}

        {searchQ.data && (
          <div className="space-y-3 max-w-3xl">
            <div className="text-xs text-zinc-500">
              {searchQ.data.total_results} results for{" "}
              <span className="text-zinc-300">“{searchQ.data.query}”</span>{" "}
              across {searchQ.data.collections_searched.join(", ")}
            </div>

            {searchQ.data.results.length === 0 && (
              <div className="text-sm text-zinc-500 mt-6">
                Nothing matched. Try broader phrasing, fewer filters, or check
                that this universe has ingested content.
              </div>
            )}

            {searchQ.data.results.map((r) => (
              <ResultCard key={`${r.collection}:${r.id}`} result={r} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ResultCard({ result }: { result: SearchResultItem }) {
  const name =
    (result.payload?.name as string) ||
    (result.payload?.title as string) ||
    truncate(result.text ?? "", 80) ||
    result.id;

  const href =
    result.collection === "entities" && result.universe_id
      ? `/explorer?universe=${result.universe_id}`
      : undefined;

  const body = (
    <div className="bg-zinc-900/60 border border-zinc-800 hover:border-zinc-700 rounded-lg px-4 py-3 transition-colors">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-zinc-100 truncate">
            {name}
          </span>
          {result.entity_type && (
            <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/30">
              {result.entity_type}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-[10px] uppercase tracking-wide text-zinc-500">
            {result.collection}
          </span>
          <span className="text-xs font-mono text-cyan-400">
            {(result.score * 100).toFixed(0)}%
          </span>
        </div>
      </div>
      {result.text && (
        <p className="mt-1 text-xs text-zinc-400 leading-relaxed">
          {truncate(result.text, 240)}
        </p>
      )}
    </div>
  );

  return href ? <Link href={href}>{body}</Link> : body;
}
