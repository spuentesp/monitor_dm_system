"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Renders LLM prose as markdown. Bold = dialogue, italic = action. */
export function ProseBubble({ children }: { children: string }) {
  return (
    <div className="prose-bubble">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children: c }) => <p className="mb-1.5 last:mb-0 leading-relaxed">{c}</p>,
          strong: ({ children: c }) => (
            <strong className="font-semibold text-slate-100">{c}</strong>
          ),
          em: ({ children: c }) => (
            <em className="italic text-slate-400">{c}</em>
          ),
          code: ({ children: c, className }) => {
            const isBlock = !!className;
            return isBlock ? (
              <code className="block bg-black/30 rounded p-2 text-xs font-mono text-cyan-300 overflow-x-auto">
                {c}
              </code>
            ) : (
              <code className="bg-white/10 px-1 rounded text-xs font-mono text-cyan-300">
                {c}
              </code>
            );
          },
          ul: ({ children: c }) => <ul className="list-disc pl-4 space-y-0.5">{c}</ul>,
          ol: ({ children: c }) => <ol className="list-decimal pl-4 space-y-0.5">{c}</ol>,
          li: ({ children: c }) => <li className="leading-relaxed">{c}</li>,
          hr: () => <hr className="border-white/10 my-2" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}