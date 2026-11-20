"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, Eye, RotateCcw, Sparkles } from "lucide-react";

import type { QuickAction } from "@/features/chat";
import type { ImageSuggestionMeta } from "@/features/chat/types";
import type { Message } from "@/lib/types";

import { extractTurnImageSuggestions } from "../playConsoleHelpers";

/**
 * Derives everything the console renders "from the latest GM turn":
 *
 * - quick-action chips (suggested next moves, guided-start options, the
 *   static Look-around / Oracle / Recap actions, and Retry-last)
 * - the current turn's image-suggestion chips (with per-session dismissal)
 *
 * Extracted from PlayConsole.tsx (UX-6 split) — behavior unchanged.
 */
export function usePlaySuggestions({
  messages,
  sessionId,
  suggestionsEnabled,
}: {
  messages: Message[];
  sessionId: string | null;
  /** False hides image-suggestion chips (image-generation settings off). */
  suggestionsEnabled: boolean;
}): {
  quickActions: QuickAction[];
  visibleImageSuggestions: ImageSuggestionMeta[];
  settleImageSuggestion: (id: string) => void;
} {
  // Image suggestions from the latest GM turn (Task 9). Chips never generate
  // on their own — a click fires the scene/portrait endpoint; dismiss or an
  // approve/reject decision settles the chip and removes it locally.
  const [settledSuggestionIds, setSettledSuggestionIds] = useState<ReadonlySet<string>>(new Set());
  const settleImageSuggestion = useCallback((id: string) => {
    setSettledSuggestionIds((prev) => new Set(prev).add(id));
  }, []);
  useEffect(() => setSettledSuggestionIds(new Set()), [sessionId]);

  // Suggested next moves from the latest GM turn (Narrator suggested_actions).
  // Rendered as fill-chips so they beat blank-page paralysis without railroading
  // the player — tap to place in the input, then send or edit.
  const lastGmMsg = [...messages].reverse().find((m) => m.role === "gm");

  const visibleImageSuggestions = useMemo(
    () =>
      suggestionsEnabled
        ? extractTurnImageSuggestions(lastGmMsg?.metadata as Record<string, unknown> | undefined).filter(
            (s) => !settledSuggestionIds.has(s.suggestion_id),
          )
        : [],
    [lastGmMsg, settledSuggestionIds, suggestionsEnabled],
  );

  const rawMeta = (lastGmMsg?.metadata ?? {}) as {
    suggested_actions?: unknown;
    suggested_answers?: unknown;
    start_options?: unknown;
  };
  const rawSuggestions = rawMeta.suggested_actions;
  // Pre-play chips (guided start): the world seed's start options and the
  // current question's suggested answers, shown the same way suggested
  // actions work in play — tap to place in the input, then send or edit.
  const startOptionChips: QuickAction[] = (
    Array.isArray(rawMeta.start_options)
      ? rawMeta.start_options.filter(
          (o): o is { title?: string; summary?: string; hook?: string } =>
            typeof o === "object" && o !== null && typeof (o as { title?: unknown }).title === "string",
        )
      : []
  ).map((option) => ({
    label: option.title ?? "",
    icon: Sparkles,
    onClick: "fill" as const,
    text: option.title ?? "",
    className: "hover:border-purple-500/30 hover:bg-purple-500/10",
    title: [option.summary, option.hook].filter(Boolean).join(" — ") || "A way to begin — tap to place in the input",
  }));
  const suggestedAnswerChips: QuickAction[] = (
    Array.isArray(rawMeta.suggested_answers)
      ? rawMeta.suggested_answers.filter((s): s is string => typeof s === "string" && s.trim().length > 0)
      : []
  )
    // The start question's suggestions repeat the option titles — the
    // start-option chips already show those, so only the extra ones
    // (e.g. "Surprise me") are rendered here.
    .filter((text) => !startOptionChips.some((chip) => chip.label === text))
    .slice(0, 3)
    .map((text) => ({
      label: text,
      icon: Sparkles,
      onClick: "fill" as const,
      text,
      className: "hover:border-cyan-500/30 hover:bg-cyan-500/10",
      title: "Suggested answer — tap to place in the input",
    }));
  const suggestionChips: QuickAction[] = [
    ...startOptionChips,
    ...suggestedAnswerChips,
    ...(Array.isArray(rawSuggestions)
      ? rawSuggestions.filter((s): s is string => typeof s === "string" && s.trim().length > 0)
      : []
    )
      .slice(0, 3)
      .map((text) => ({
        label: text,
        icon: Sparkles,
        onClick: "fill" as const,
        text,
        className: "hover:border-cyan-500/30 hover:bg-cyan-500/10",
        title: "Suggested next move — tap to place in the input",
      })),
  ];

  const quickActions: QuickAction[] = [
    ...suggestionChips,
    {
      label: "Look around",
      icon: Eye,
      onClick: "submit",
      text: "I pause and take in my surroundings — what do I see, hear, and notice?",
    },
    {
      label: "Ask the Oracle",
      icon: Sparkles,
      onClick: "fill",
      text: "(( Oracle: ",
      className: "hover:border-purple-500/30 hover:bg-purple-500/10",
      title: "Ask the oracle a yes/no question about the world",
    },
    {
      label: "Story so far",
      icon: BookOpen,
      onClick: "fill",
      text: "/recap",
      className: "hover:border-amber-500/30 hover:bg-amber-500/10",
    },
    ...(messages.some((m) => m.role === "player")
      ? [
          {
            label: "Retry last",
            icon: RotateCcw,
            onClick: "submit" as const,
            text: messages
              .slice()
              .reverse()
              .find(
                (m) =>
                  m.role === "player" &&
                  (m.metadata as { type?: string })?.type !== "dice_result",
              )?.content ?? "",
            className: "hover:border-cyan-500/30 hover:bg-cyan-500/10",
            title: "Re-send your previous action",
            disabled: !messages
              .slice()
              .reverse()
              .some(
                (m) =>
                  m.role === "player" &&
                  (m.metadata as { type?: string })?.type !== "dice_result",
              ),
          },
        ]
      : []),
  ];

  return { quickActions, visibleImageSuggestions, settleImageSuggestion };
}
