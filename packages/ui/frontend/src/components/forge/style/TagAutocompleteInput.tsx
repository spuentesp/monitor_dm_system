"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toneApi } from "@/lib/api";

/**
 * Comma-separated tags input with autocomplete backed by the tag registry
 * (F3-4.3). The "partial" is the segment after the last comma; picking a
 * suggestion replaces that segment in place.
 */
export function TagAutocompleteInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
}) {
  const [focused, setFocused] = useState(false);

  const lastSegment = value.split(",").pop() ?? "";
  const partial = lastSegment.trim();
  const existing = new Set(
    value
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
  );

  const suggestQ = useQuery({
    queryKey: ["tone", "tagSuggest", partial],
    queryFn: () => toneApi.suggestTags(partial, { limit: 8 }),
    enabled: focused && partial.length >= 1,
    staleTime: 30_000,
  });

  const suggestions = (suggestQ.data?.suggestions ?? []).filter(
    (s) => !existing.has(s.tag),
  );

  const pick = (tag: string) => {
    const head = value.slice(0, value.length - lastSegment.length);
    onChange(`${head}${head && !head.endsWith(" ") ? " " : ""}${tag}`);
  };

  return (
    <div className="relative">
      <input
        aria-label={ariaLabel}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder={placeholder}
        autoComplete="off"
        className={`w-full ${className ?? ""}`}
      />
      {focused && suggestions.length > 0 && (
        <ul
          role="listbox"
          aria-label="Tag suggestions"
          className="absolute z-20 mt-1 w-full max-h-48 overflow-y-auto bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl"
        >
          {suggestions.map((s) => (
            <li key={s.tag}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onMouseDown={(e) => {
                  // mousedown fires before blur, so the pick lands before the
                  // dropdown hides.
                  e.preventDefault();
                  pick(s.tag);
                }}
                className="w-full text-left px-3 py-1.5 text-sm text-slate-200 hover:bg-zinc-800"
              >
                {s.tag}
                {s.description && (
                  <span className="ml-2 text-xs text-slate-500">{s.description}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
