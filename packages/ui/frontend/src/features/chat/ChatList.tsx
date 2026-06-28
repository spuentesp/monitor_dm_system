"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { AnimatePresence } from "framer-motion";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";
import type { ThinkingTrace, ToolCall } from "./types";
import { AlertCircle, ChevronDown, RotateCcw, X } from "lucide-react";
import type { Message } from "@/lib/types";
import type { DiceRequest, StreamingMessage, TurnFailure } from "./types";
import { TypingIndicator } from "./TypingIndicator";
import { DiceRollPrompt } from "./DiceRollPrompt";

export interface ChatListProps {
  messages: Message[];
  streamingMsg: StreamingMessage | null;
  isTyping: boolean;
  sendFailure: TurnFailure | null;
  pendingDiceRequest: DiceRequest | null;
  /** Render an individual message bubble. */
  renderBubble: (msg: Message & { streaming?: string }) => React.ReactNode;
  /** Called when the user confirms a dice roll. */
  onDiceResult: (spec: string, value: number, rolls: number[], reason: string) => void;
  /** Called when the user clicks Retry on the failure card. */
  onRetry?: () => void;
  /** Called when the user clicks Dismiss on the failure card. */
  onDismissFailure?: () => void;
  /** Empty-state slot (rendered when there are no messages). */
  emptyState?: React.ReactNode;
  /** Tail-align items (default true — chat bubbles reverse to bottom). */
  alignToBottom?: boolean;
}

/**
 * Virtualized message list with built-in sticky-scroll.
 *
 * Uses react-virtuoso's `followOutput` for the "only auto-scroll if user
 * is near the bottom" behavior — same intent as the old useStickyScroll
 * hook, but native to the virtualized scroller so it survives dynamic
 * heights (markdown bubbles, dice cards, etc.).
 */
export function ChatList({
  messages,
  streamingMsg,
  isTyping,
  sendFailure,
  pendingDiceRequest,
  renderBubble,
  onDiceResult,
  onRetry,
  onDismissFailure,
  emptyState,
  alignToBottom = true,
}: ChatListProps) {
  const virtuosoRef = useRef<VirtuosoHandle | null>(null);

  // When streamingMsg lands, ensure the streaming bubble is visible.
  useEffect(() => {
    if (!streamingMsg) return;
    virtuosoRef.current?.scrollIntoView({ index: messages.length, behavior: "smooth", align: "end" });
    // We intentionally re-fire only when streamingMsg identity changes, not
    // on every keystroke. The "smooth" animation plus react-virtuoso's
    // followOutput handles the rest.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamingMsg?.id]);

  const items: Array<Message & { streaming?: string; thinking?: ThinkingTrace; toolCalls?: ToolCall[] }> = [...messages];
  if (streamingMsg) {
    // Local alias narrows the type for the spread below.
    const liveThinking = streamingMsg.thinking;
    const liveToolCalls = streamingMsg.toolCalls;
    items.push({
      id: streamingMsg.id,
      session_id: "",
      role: "gm",
      content: "",
      timestamp: new Date().toISOString(),
      metadata: {},
      streaming: streamingMsg.text,
      thinking: liveThinking,
      toolCalls: liveToolCalls,
    });
  }

  const itemContent = useCallback(
    (_index: number, msg: Message & { streaming?: string; thinking?: ThinkingTrace; toolCalls?: ToolCall[] }) => (
      <div className="px-6 py-2">
        {renderBubble(msg)}
      </div>
    ),
    [renderBubble],
  );

  const virtuosoComponents = useMemo(
    () => ({
      Footer: () => (
        <div className="px-6 py-3 space-y-3">
          <AnimatePresence>
            {isTyping && !streamingMsg && <TypingIndicator key="typing" />}
          </AnimatePresence>

          <AnimatePresence>
            {sendFailure && !isTyping && !streamingMsg && (
              <div
                key="failure"
                className="rounded-xl border border-red-500/25 bg-red-500/5 px-4 py-3 space-y-2"
              >
                <div className="flex items-center gap-2 text-xs text-red-300 font-medium">
                  <AlertCircle className="w-3.5 h-3.5" />
                  Turn didn&apos;t go through
                </div>
                <p className="text-xs text-slate-400 leading-relaxed break-words">
                  {sendFailure.detail}
                </p>
                <div className="flex items-center gap-2">
                  {sendFailure.text && onRetry && (
                    <button onClick={onRetry} className="btn-cyber text-xs py-1 px-3">
                      <RotateCcw className="w-3 h-3" /> Retry
                    </button>
                  )}
                  {onDismissFailure && (
                    <button
                      onClick={onDismissFailure}
                      className="btn-ghost text-xs py-1 px-2 text-slate-500"
                    >
                      <X className="w-3 h-3" /> Dismiss
                    </button>
                  )}
                </div>
              </div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {pendingDiceRequest && !isTyping && (
              <DiceRollPrompt
                key="dice-prompt"
                request={pendingDiceRequest}
                onResult={onDiceResult}
              />
            )}
          </AnimatePresence>
        </div>
      ),
    }),
    [isTyping, streamingMsg, sendFailure, onRetry, onDismissFailure, pendingDiceRequest, onDiceResult],
  );

  const hasContent = items.length > 0 || isTyping || !!pendingDiceRequest || !!sendFailure;

  return (
    <div className="relative flex-1 min-h-0">
      {!hasContent && emptyState ? (
        <div className="h-full">{emptyState}</div>
      ) : (
        <Virtuoso
          // Render all items on first mount so the bubbles are present
          // immediately (and so tests don't have to fight virtuoso's
          // IntersectionObserver-driven virtualization in happy-dom).
          // Subsequent updates still virtualize above this cap.
          initialItemCount={Math.min(items.length, 50)}
          ref={virtuosoRef}
          className="h-full"
          data={items}
          alignToBottom={alignToBottom}
          followOutput={isTyping || !!streamingMsg ? "smooth" : false}
          increaseViewportBy={{ top: 200, bottom: 200 }}
          itemContent={itemContent}
          components={virtuosoComponents}
        />
      )}
    </div>
  );
}