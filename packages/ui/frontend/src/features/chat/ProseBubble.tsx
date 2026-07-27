"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** One ((...)) span vs. everything around it, in order of appearance. */
export interface NarrationBlock {
  ooc: boolean;
  text: string;
}

const OOC_BLOCK_RE = /\({2,}([\s\S]*?)\){2,}/g;

/**
 * Split GM narration into narration/OOC chunks.
 *
 * ((double parentheses)) mark a fourth-wall-breaking OOC aside (rules
 * answers, meta commands, direct address to the player); everything else
 * is in-fiction narration/dialogue and renders through the normal markdown
 * path (*action* italics are native markdown — no split needed for that
 * marker). Empty chunks (consecutive markers, whitespace-only spans) are
 * dropped. Mirrors `_split_narration_blocks` in the CLI's `play.py`.
 */
export function splitNarrationBlocks(text: string): NarrationBlock[] {
  const blocks: NarrationBlock[] = [];
  let pos = 0;
  for (const match of text.matchAll(OOC_BLOCK_RE)) {
    const before = text.slice(pos, match.index).trim();
    if (before) blocks.push({ ooc: false, text: before });
    const oocText = match[1].trim();
    if (oocText) blocks.push({ ooc: true, text: oocText });
    pos = (match.index ?? 0) + match[0].length;
  }
  const tail = text.slice(pos).trim();
  if (tail) blocks.push({ ooc: false, text: tail });
  return blocks;
}

/** GM stepping outside the fiction — rules answers, meta replies, asides. */
function OOCBlock({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-2 my-1.5 first:mt-0 last:mb-0 text-amber-100">
      <div className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-300/80">
        OOC
      </div>
      <p className="leading-relaxed">{children}</p>
    </div>
  );
}

const markdownComponents = {
  p: ({ children: c }: { children?: React.ReactNode }) => (
    <p className="mb-1.5 last:mb-0 leading-relaxed">{c}</p>
  ),
  strong: ({ children: c }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-slate-100">{c}</strong>
  ),
  em: ({ children: c }: { children?: React.ReactNode }) => (
    <em className="italic text-slate-400">{c}</em>
  ),
  code: ({ children: c, className }: { children?: React.ReactNode; className?: string }) => {
    const isBlock = !!className;
    return isBlock ? (
      <code className="block bg-black/30 rounded p-2 text-xs font-mono text-cyan-300 overflow-x-auto">
        {c}
      </code>
    ) : (
      <code className="bg-white/10 px-1 rounded text-xs font-mono text-cyan-300">{c}</code>
    );
  },
  ul: ({ children: c }: { children?: React.ReactNode }) => (
    <ul className="list-disc pl-4 space-y-0.5">{c}</ul>
  ),
  ol: ({ children: c }: { children?: React.ReactNode }) => (
    <ol className="list-decimal pl-4 space-y-0.5">{c}</ol>
  ),
  li: ({ children: c }: { children?: React.ReactNode }) => (
    <li className="leading-relaxed">{c}</li>
  ),
  hr: () => <hr className="border-white/10 my-2" />,
};

/**
 * Renders LLM prose as markdown. *italic* = action (real SillyTavern
 * convention); plain text = dialogue/narration (the default); bold is
 * generic emphasis, not a semantic marker. ((double parentheses)) split
 * out into a distinct OOC block instead of running through markdown.
 */
export function ProseBubble({ children }: { children: string }) {
  const blocks = splitNarrationBlocks(children);
  // No OOC markers at all — render the whole string as before (avoids
  // the split allocation on the common, unmarked-text path).
  if (blocks.length <= 1 && !blocks[0]?.ooc) {
    return (
      <div className="prose-bubble">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {children}
        </ReactMarkdown>
      </div>
    );
  }
  return (
    <div className="prose-bubble">
      {blocks.map((block, i) =>
        block.ooc ? (
          <OOCBlock key={i}>{block.text}</OOCBlock>
        ) : (
          <ReactMarkdown key={i} remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {block.text}
          </ReactMarkdown>
        ),
      )}
    </div>
  );
}
