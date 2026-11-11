"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, BookOpen, Download, FileText, Loader2, Users } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { shareApi, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * CF-14 — public player view behind a share token (G07).
 *
 * Unauthenticated by design: the token in the path is the credential. The
 * server has already filtered drafts, revoked links, and character-scoped
 * spoilers; this page only renders what /api/share returns.
 */
export default function SharePage() {
  const params = useParams<{ token: string }>();
  const token = typeof params?.token === "string" ? params.token : "";

  const [viewerCharacter, setViewerCharacter] = useState<string>("");
  const [openId, setOpenId] = useState<string | null>(null);

  const viewQuery = useQuery({
    queryKey: ["share-view", token, viewerCharacter],
    queryFn: () => shareApi.view(token, viewerCharacter || null),
    enabled: token.length > 0,
    retry: false,
    staleTime: 15_000,
  });

  const detailQuery = useQuery({
    queryKey: ["share-detail", token, openId, viewerCharacter],
    queryFn: () => {
      const artifact = viewQuery.data?.artifacts.find((a) => a.id === openId);
      if (!artifact) throw new Error("artifact not in view");
      return artifact.artifact_type === "recap"
        ? shareApi.recap(token, openId!, viewerCharacter || null)
        : shareApi.handout(token, openId!, viewerCharacter || null);
    },
    enabled: token.length > 0 && openId !== null,
    retry: false,
    staleTime: 60_000,
  });

  const characters = viewQuery.data?.characters ?? [];
  const artifacts = viewQuery.data?.artifacts ?? [];

  const openArtifact = useMemo(
    () => artifacts.find((a) => a.id === openId) ?? null,
    [artifacts, openId],
  );

  if (viewQuery.isPending && token) {
    return (
      <main className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-500 text-sm" data-testid="share-loading">
          <Loader2 className="w-4 h-4 animate-spin" /> Gathering what your party may see…
        </div>
      </main>
    );
  }

  if (viewQuery.isError) {
    const status = viewQuery.error instanceof ApiError ? viewQuery.error.status : 0;
    const revoked = status === 404;
    const limited = status === 429;
    return (
      <main className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
        <div
          className="max-w-md w-full text-center space-y-3 py-10"
          data-testid="share-unavailable"
        >
          <AlertCircle className="w-8 h-8 mx-auto text-slate-600" />
          <h1 className="text-lg font-semibold text-slate-200">
            {limited ? "Too many requests" : "This share link is no longer available"}
          </h1>
          <p className="text-sm text-slate-500">
            {limited
              ? "Wait a moment and try again."
              : "Ask your GM for a fresh link — it may have been revoked or expired."}
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-200">
      <div className="max-w-2xl mx-auto px-4 py-10 space-y-6">
        <header className="space-y-1" data-testid="share-header">
          <div className="flex items-center gap-2 text-amber-400">
            <BookOpen className="w-4 h-4" />
            <span className="text-[10px] font-semibold uppercase tracking-widest">
              Shared with the party
            </span>
          </div>
          <h1 className="text-xl font-semibold text-slate-100">Session recaps &amp; handouts</h1>
          <p className="text-xs text-slate-500">
            Read-only. What you see here is exactly what your GM published.
          </p>
        </header>

        {characters.length > 0 && (
          <label
            className="flex items-center gap-2 text-xs text-slate-400"
            data-testid="share-character-picker"
          >
            <Users className="w-3.5 h-3.5" />
            Viewing as
            <select
              value={viewerCharacter}
              onChange={(e) => {
                setViewerCharacter(e.target.value);
                setOpenId(null);
              }}
              className="input-cyber py-1 text-xs max-w-[200px]"
            >
              <option value="">The whole party</option>
              {characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}

        {artifacts.length === 0 ? (
          <p className="text-sm text-slate-600 py-8 text-center" data-testid="share-empty">
            Nothing has been published yet — check back after the next session.
          </p>
        ) : (
          <ul className="space-y-2" data-testid="share-artifact-list">
            {artifacts.map((artifact) => (
              <li key={artifact.id} className="rounded-xl border border-white/10 bg-white/[0.03]">
                <button
                  onClick={() => setOpenId(openId === artifact.id ? null : artifact.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/5 transition-colors"
                  data-testid={`share-artifact-${artifact.id}`}
                >
                  {artifact.artifact_type === "recap" ? (
                    <BookOpen className="w-4 h-4 text-amber-400 flex-shrink-0" />
                  ) : (
                    <FileText className="w-4 h-4 text-purple-400 flex-shrink-0" />
                  )}
                  <span className="flex-1 text-sm font-medium text-slate-200">{artifact.title}</span>
                  <span
                    className={cn(
                      "text-[10px] px-1.5 py-0.5 rounded",
                      artifact.spoiler_level === "character"
                        ? "bg-amber-500/15 text-amber-400"
                        : "bg-emerald-500/10 text-emerald-400",
                    )}
                  >
                    {artifact.spoiler_level === "character" ? "your character" : "party"}
                  </span>
                  <span className="text-[10px] text-slate-600">
                    {new Date(artifact.updated_at).toLocaleDateString()}
                  </span>
                </button>

                {openId === artifact.id && (
                  <div className="border-t border-white/5 px-4 py-4 space-y-3" data-testid="share-artifact-detail">
                    {detailQuery.isPending ? (
                      <div className="flex items-center gap-2 text-xs text-slate-500">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
                      </div>
                    ) : detailQuery.isError ? (
                      <p className="text-xs text-red-400">
                        {detailQuery.error instanceof ApiError && detailQuery.error.status === 404
                          ? "You can't see this one — it may be scoped to another character."
                          : "Couldn't load this right now."}
                      </p>
                    ) : detailQuery.data ? (
                      <>
                        <div className="prose-bubble text-sm text-slate-300 leading-relaxed">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {detailQuery.data.content}
                          </ReactMarkdown>
                        </div>
                        <a
                          href={shareApi.exportUrl(token, artifact.id, viewerCharacter || null)}
                          download
                          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 border border-white/10 rounded-lg px-2.5 py-1"
                          data-testid={`share-export-${artifact.id}`}
                        >
                          <Download className="w-3 h-3" /> Download .md
                        </a>
                      </>
                    ) : null}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
