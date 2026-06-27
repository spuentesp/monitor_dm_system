"use client";

import { motion } from "framer-motion";
import { Bot, Dices, User } from "lucide-react";
import type { Message } from "@/lib/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { CopyButton } from "@/features/chat/CopyButton";
import { DiceResultCard } from "@/features/chat/DiceResultCard";
import { ProseBubble } from "@/features/chat/ProseBubble";
import { ThinkingBubble } from "@/features/chat/ThinkingBubble";
import { ToolCallCard } from "@/features/chat/ToolCallCard";
import type { ThinkingTrace } from "@/features/chat";

interface BubbleMetadata {
  type?: string;
  intent_type?: string;
  success_level?: string;
  roll_breakdown?: string;
  roll_detail?: { spec: string; total: number; rolls: number[]; reason?: string };
  dice_result?: { spec: string; value: number; rolls?: number[]; reason?: string };
  effects?: string[];
  risk_preview?: string;
  consequence_options?: string[];
  requires_player_choice?: boolean;
  narrative_pressure?: string;
  social_read?: {
    stance_after?: string;
    reason?: string;
    confidence?: number;
    deltas?: Record<string, number>;
  };
  relationship_snapshot?: Record<string, unknown>;
  /** Persisted reasoning text — populated by useChatSession when the
   *  server emits `thinking` chunks before the narrative. */
  thinking?: string;
}

/**
 * PlayConsole-specific message bubble. Renders GM prose with dice cards,
 * risk previews, social continuity chips, and a copy button. Used as the
 * `renderBubble` callback for `<ChatList/>`.
 *
 * The optional `thinking` field carries a live `ThinkingTrace` while the
 * model is generating reasoning; once the trace is finalized the text
 * is persisted on `metadata.thinking` and the bubble continues to render
 * it (now collapsible, auto-collapsed).
 */
export function PlayMessageBubble({
  msg,
}: {
  msg: Message & { streaming?: string; thinking?: ThinkingTrace; toolCalls?: Array<{ id: string; name: string; args: Record<string, unknown>; result_preview?: string; error?: string; pending: boolean }> };
}) {
  const isGM = msg.role === "gm";
  const isSystem = msg.role === "system";
  const meta = (msg.metadata ?? {}) as BubbleMetadata;

  // Live trace (only present on the streaming bubble). Falls through to
  // the persisted metadata once the message is committed.
  const thinkingTrace: ThinkingTrace | null =
    msg.thinking ??
    (meta.thinking
      ? { message_id: msg.id, text: meta.thinking, streaming: false }
      : null);

  if (isSystem) {
    return (
      <div className="flex justify-center">
        <div className="msg-system rounded-lg px-3 py-1.5 text-xs text-slate-500 max-w-md text-center">
          <ProseBubble>{msg.content}</ProseBubble>
        </div>
      </div>
    );
  }

  const isDiceResultMsg = meta.type === "dice_result" && !isGM;
  const socialDeltaEntries = Object.entries(meta.social_read?.deltas ?? {}).slice(0, 4);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn("group/bubble flex items-end gap-2", !isGM && "flex-row-reverse")}
    >
      <div
        className={cn(
          "w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 border",
          isGM
            ? "bg-purple-500/20 border-purple-500/30"
            : isDiceResultMsg
              ? "bg-amber-500/20 border-amber-500/30"
              : "bg-cyan-500/20 border-cyan-500/30",
        )}
      >
        {isGM ? (
          <Bot className="w-3 h-3 text-purple-400" />
        ) : isDiceResultMsg ? (
          <Dices className="w-3 h-3 text-amber-400" />
        ) : (
          <User className="w-3 h-3 text-cyan-400" />
        )}
      </div>

      <div
        className={cn(
          "max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed",
          isGM
            ? "msg-gm rounded-bl-sm"
            : isDiceResultMsg
              ? "rounded-br-sm bg-amber-500/5 border border-amber-500/20"
              : "msg-player rounded-br-sm",
        )}
      >
        {"streaming" in msg && msg.streaming !== undefined ? (
          <span>
            <ProseBubble>{msg.streaming}</ProseBubble>
            <span className="inline-block w-0.5 h-4 bg-purple-400 ml-0.5 animate-pulse align-middle" />
          </span>
        ) : (
          <ProseBubble>{msg.content}</ProseBubble>
        )}

        {/* Reasoning trace — visible while streaming, persisted + collapsible after. */}
        {isGM && thinkingTrace && (
          <ThinkingBubble trace={thinkingTrace} />
        )}

        {/* Phase 2B: MCP tool invocations surfaced by the agent. Rendered
            below the prose bubble, one card per tool call. The same list
            lives on metadata.tool_calls after the turn completes. */}
        {isGM && msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="space-y-1">
            {msg.toolCalls.map((tc) => (
              <ToolCallCard key={tc.id} call={tc} />
            ))}
          </div>
        )}

        {/* Inline dice result card (from agent resolution metadata) */}
        {isGM && meta.roll_detail && (
          <DiceResultCard
            spec={meta.roll_detail.spec}
            total={meta.roll_detail.total}
            rolls={meta.roll_detail.rolls}
            reason={meta.roll_detail.reason}
            successLevel={meta.success_level}
          />
        )}

        {/* Compact roll breakdown (legacy metadata) */}
        {isGM && !meta.roll_detail && meta.roll_breakdown && (
          <div className="mt-2 rounded-lg border border-purple-500/20 bg-purple-500/5 px-2.5 py-2 text-[11px] text-purple-100">
            <div className="font-medium text-purple-300">Resolution</div>
            <div className="mt-0.5">{meta.roll_breakdown}</div>
          </div>
        )}

        {isGM &&
          (meta.risk_preview ||
            (Array.isArray(meta.consequence_options) && meta.consequence_options.length > 0)) && (
            <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-2 text-[11px] text-amber-100">
              {meta.intent_type && (
                <div className="mb-1 text-amber-300 font-medium capitalize">
                  {meta.intent_type.replace(/_/g, " ")}
                  {meta.narrative_pressure ? ` · pressure ${meta.narrative_pressure}` : ""}
                </div>
              )}
              {meta.risk_preview && <p>{meta.risk_preview}</p>}
              {Array.isArray(meta.consequence_options) && meta.consequence_options.length > 0 && (
                <div className="mt-1.5 space-y-1">
                  <div className="font-medium text-amber-300">
                    {meta.requires_player_choice
                      ? "Suggested consequence choices"
                      : "Likely follow-through"}
                  </div>
                  <ul className="list-disc pl-4 space-y-0.5">
                    {meta.consequence_options.slice(0, 3).map((option) => (
                      <li key={option}>{option}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

        {isGM &&
          (meta.social_read?.stance_after ||
            Object.keys(meta.relationship_snapshot ?? {}).length > 0) && (
            <div className="mt-2 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-2.5 py-2 text-[11px] text-cyan-100">
              <div className="font-medium text-cyan-300">Social continuity</div>
              {meta.social_read?.stance_after && (
                <div className="mt-1">
                  <span className="text-slate-300">Stance:</span> {meta.social_read.stance_after}
                </div>
              )}
              {socialDeltaEntries.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {socialDeltaEntries.map(([key, value]) => (
                    <span key={key} className="tag-dim">
                      {key} {value >= 0 ? "+" : ""}
                      {value.toFixed(2)}
                    </span>
                  ))}
                </div>
              )}
              {meta.social_read?.reason && (
                <p className="mt-1.5 leading-relaxed text-cyan-50/90">{meta.social_read.reason}</p>
              )}
            </div>
          )}

        <div
          className={cn(
            "flex items-center gap-2 text-[10px] mt-1.5",
            isGM ? "text-purple-200" : isDiceResultMsg ? "text-amber-200" : "text-cyan-200",
          )}
        >
          <span className="opacity-40">{formatRelativeTime(msg.timestamp)}</span>
          {isGM && msg.content && !("streaming" in msg && msg.streaming !== undefined) && (
            <span className="opacity-0 group-hover/bubble:opacity-100 transition-opacity">
              <CopyButton text={msg.content} />
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
}