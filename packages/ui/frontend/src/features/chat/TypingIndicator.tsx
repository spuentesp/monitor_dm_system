"use client";

import { Bot } from "lucide-react";

/** Three pulsing dots inside a GM bubble. */
export function TypingIndicator() {
  return (
    <div role="status" aria-label="GM is typing" className="flex items-end gap-2 animate-fade-in">
      <div className="w-6 h-6 rounded-full bg-purple-500/20 border border-purple-500/30 flex items-center justify-center flex-shrink-0">
        <Bot className="w-3 h-3 text-purple-400" />
      </div>
      <div className="msg-gm rounded-xl rounded-bl-sm px-4 py-3">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-purple-400 typing-dot" />
          <div className="w-1.5 h-1.5 rounded-full bg-purple-400 typing-dot" />
          <div className="w-1.5 h-1.5 rounded-full bg-purple-400 typing-dot" />
        </div>
      </div>
    </div>
  );
}