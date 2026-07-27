"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Loader2 } from "lucide-react";
import { DialogShell, DialogFooter } from "@/components/DialogShell";
import { templatesApi } from "@/lib/api";
import type { EntityTemplate } from "@/lib/types";

// ═══════════════════════════════════════════════════════════════
//  Template Editor Modal (create + edit modes) — F3-2b
// ═══════════════════════════════════════════════════════════════

/** Backend EntityType enum (monitor_data.schemas.base.EntityType). */
const ENTITY_TYPES = ["character", "faction", "location", "object", "concept", "organization"];
const DETAIL_LEVELS = ["stub", "sketched", "detailed", "elaborated"];

interface TemplateEditorModalProps {
  /** null → create mode; template → edit mode. */
  template: EntityTemplate | null;
  universeId: string;
  onClose: () => void;
}

interface JsonFieldState {
  text: string;
  error: string | null;
}

function toJsonState(value: unknown, fallback: string): JsonFieldState {
  return { text: value == null ? fallback : JSON.stringify(value, null, 2), error: null };
}

/** Parse a JSON textarea; empty → null, invalid → undefined + field error. */
function parseJsonField(
  state: JsonFieldState,
  setError: (error: string | null) => void,
): unknown | undefined {
  const trimmed = state.text.trim();
  if (!trimmed) {
    setError(null);
    return null;
  }
  try {
    const parsed = JSON.parse(trimmed);
    setError(null);
    return parsed;
  } catch {
    setError("Invalid JSON");
    return undefined;
  }
}

function JsonTextarea({
  label,
  state,
  onChange,
  rows = 3,
  hint,
}: {
  label: string;
  state: JsonFieldState;
  onChange: (s: JsonFieldState) => void;
  rows?: number;
  hint?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-[10px] font-bold tracking-widest uppercase text-slate-500">{label}</label>
      <textarea
        value={state.text}
        onChange={(e) => onChange({ text: e.target.value, error: null })}
        rows={rows}
        spellCheck={false}
        aria-label={label}
        className="input-cyber py-1.5 text-xs w-full font-mono resize-y"
      />
      {state.error ? (
        <p className="text-[10px] text-red-400">{state.error}</p>
      ) : hint ? (
        <p className="text-[10px] text-slate-600">{hint}</p>
      ) : null}
    </div>
  );
}

export function TemplateEditorModal({ template, universeId, onClose }: TemplateEditorModalProps) {
  const isEdit = template !== null;
  const queryClient = useQueryClient();

  const [name, setName] = useState(template?.name ?? "");
  const [description, setDescription] = useState(template?.description ?? "");
  const [entityType, setEntityType] = useState(template?.entity_type ?? "character");
  const [detailLevel, setDetailLevel] = useState(template?.default_detail_level ?? "stub");
  const [stateTags, setStateTags] = useState((template?.default_state_tags ?? []).join(", "));
  const [parentId, setParentId] = useState(template?.parent_template_id ?? "");
  const [baseProps, setBaseProps] = useState<JsonFieldState>(
    toJsonState(template?.base_properties, "{}"),
  );
  const [variableProps, setVariableProps] = useState<JsonFieldState>(
    toJsonState(template?.variable_properties, "[]"),
  );
  const [namingPattern, setNamingPattern] = useState<JsonFieldState>(
    toJsonState(template?.naming_pattern, '{\n  "type": "llm"\n}'),
  );
  const [statGeneration, setStatGeneration] = useState<JsonFieldState>(
    toJsonState(template?.stat_generation, '{\n  "method": "fixed"\n}'),
  );
  const [personality, setPersonality] = useState<JsonFieldState>(
    toJsonState(template?.default_personality, ""),
  );
  const [submitError, setSubmitError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      isEdit
        ? templatesApi.update(template.template_id, payload)
        : templatesApi.create(payload as Parameters<typeof templatesApi.create>[0]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      onClose();
    },
    onError: (err: Error) => setSubmitError(err.message || "Failed to save template"),
  });

  const handleSubmit = () => {
    setSubmitError(null);
    if (!name.trim()) {
      setSubmitError("Name is required");
      return;
    }
    const parsedBase = parseJsonField(baseProps, (e) => setBaseProps((s) => ({ ...s, error: e })));
    const parsedVars = parseJsonField(variableProps, (e) => setVariableProps((s) => ({ ...s, error: e })));
    const parsedNaming = parseJsonField(namingPattern, (e) => setNamingPattern((s) => ({ ...s, error: e })));
    const parsedStats = parseJsonField(statGeneration, (e) => setStatGeneration((s) => ({ ...s, error: e })));
    const parsedPersonality = parseJsonField(personality, (e) => setPersonality((s) => ({ ...s, error: e })));

    if (
      parsedBase === undefined ||
      parsedVars === undefined ||
      parsedNaming === undefined ||
      parsedStats === undefined ||
      parsedPersonality === undefined
    ) {
      return; // field-level error already set
    }
    if (parsedVars !== null && !Array.isArray(parsedVars)) {
      setVariableProps((s) => ({ ...s, error: "Must be a JSON array" }));
      return;
    }
    const tags = stateTags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    const payload: Record<string, unknown> = {
      name: name.trim(),
      description: description.trim(),
      base_properties: parsedBase ?? {},
      variable_properties: parsedVars ?? [],
      naming_pattern: parsedNaming ?? { type: "llm" },
      stat_generation: parsedStats ?? { method: "fixed" },
      default_state_tags: tags,
      default_detail_level: detailLevel,
      default_personality: parsedPersonality ?? null,
    };

    if (isEdit) {
      mutation.mutate(payload);
    } else {
      mutation.mutate({
        ...payload,
        universe_id: universeId,
        entity_type: entityType,
        parent_template_id: parentId.trim() || null,
      });
    }
  };

  return (
    <DialogShell
      title={isEdit ? `Edit Template — ${template.name}` : "New Template"}
      icon={BookOpen}
      onClose={onClose}
      maxWidthClassName="max-w-2xl"
    >
      <div className="p-4 space-y-3 max-h-[70vh] overflow-y-auto">
        {/* Name + type row */}
        <div className="flex gap-3">
          <div className="space-y-1 flex-1">
            <label className="text-[10px] font-bold tracking-widest uppercase text-slate-500">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., City Guard"
              className="input-cyber py-1.5 text-xs w-full"
            />
          </div>
          <div className="space-y-1 w-40">
            <label className="text-[10px] font-bold tracking-widest uppercase text-slate-500">Entity Type</label>
            <select
              value={entityType}
              onChange={(e) => setEntityType(e.target.value)}
              disabled={isEdit}
              aria-label="Entity Type"
              className="input-cyber py-1.5 text-xs w-full disabled:opacity-50"
            >
              {ENTITY_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1 w-32">
            <label className="text-[10px] font-bold tracking-widest uppercase text-slate-500">Detail Level</label>
            <select
              value={detailLevel}
              onChange={(e) => setDetailLevel(e.target.value)}
              aria-label="Detail Level"
              className="input-cyber py-1.5 text-xs w-full"
            >
              {DETAIL_LEVELS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Description */}
        <div className="space-y-1">
          <label className="text-[10px] font-bold tracking-widest uppercase text-slate-500">Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            placeholder="What is this template for?"
            className="input-cyber py-1.5 text-xs w-full resize-none"
          />
        </div>

        {/* Tags + parent row */}
        <div className="flex gap-3">
          <div className="space-y-1 flex-1">
            <label className="text-[10px] font-bold tracking-widest uppercase text-slate-500">
              Default State Tags
            </label>
            <input
              value={stateTags}
              onChange={(e) => setStateTags(e.target.value)}
              placeholder="comma, separated, tags"
              className="input-cyber py-1.5 text-xs w-full"
            />
          </div>
          {!isEdit && (
            <div className="space-y-1 flex-1">
              <label className="text-[10px] font-bold tracking-widest uppercase text-slate-500">
                Parent Template ID
              </label>
              <input
                value={parentId}
                onChange={(e) => setParentId(e.target.value)}
                placeholder="optional UUID — inherit base properties"
                className="input-cyber py-1.5 text-xs w-full font-mono"
              />
            </div>
          )}
        </div>

        {/* Structured JSON fields */}
        <JsonTextarea
          label="Base Properties (JSON object)"
          state={baseProps}
          onChange={setBaseProps}
          hint="Fixed properties applied to every instance."
        />
        <JsonTextarea
          label="Variable Properties (JSON array)"
          state={variableProps}
          onChange={setVariableProps}
          rows={4}
          hint='[{"property_path": "stats.STR", "generation_type": "range", "range_min": 8, "range_max": 14}]'
        />
        <JsonTextarea
          label="Naming Pattern (JSON object)"
          state={namingPattern}
          onChange={setNamingPattern}
          hint='{"type": "pattern", "pattern": "{adjective} {noun}", "adjectives": [...], "nouns": [...]}'
        />
        <JsonTextarea
          label="Stat Generation (JSON object)"
          state={statGeneration}
          onChange={setStatGeneration}
        />
        <JsonTextarea
          label="Default Personality (JSON object, optional)"
          state={personality}
          onChange={setPersonality}
          hint="Leave empty for none."
        />

        {submitError && <p className="text-xs text-red-400">{submitError}</p>}
      </div>

      <DialogFooter>
        <button onClick={onClose} className="btn-ghost text-xs py-1.5 px-3">
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={mutation.isPending}
          className="btn-cyber text-xs py-1.5 px-4"
        >
          {mutation.isPending && <Loader2 className="w-3 h-3 animate-spin" />}
          {isEdit ? "Save Changes" : "Create Template"}
        </button>
      </DialogFooter>
    </DialogShell>
  );
}
