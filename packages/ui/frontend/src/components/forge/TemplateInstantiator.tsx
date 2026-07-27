"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Dices,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import { entitiesApi, templatesApi } from "@/lib/api";
import type { EntityTemplate } from "@/lib/types";
import { previewInstantiation } from "@/lib/templateResolve";

// ═══════════════════════════════════════════════════════════════
//  Template Instantiator Dialog (F3-2c)
// ═══════════════════════════════════════════════════════════════

interface TemplateInstantiatorProps {
  template: EntityTemplate;
  open: boolean;
  onClose: () => void;
  onCreated?: (entityId: string) => void;
}

export function TemplateInstantiator({ template, open, onClose, onCreated }: TemplateInstantiatorProps) {
  const [overrideName, setOverrideName] = useState("");
  const [context, setContext] = useState("");
  const [step, setStep] = useState<"configure" | "creating" | "done">("configure");
  const queryClient = useQueryClient();

  // Client-side preview of what the server will resolve (F3-2c).
  const preview = useMemo(
    () => previewInstantiation(template, overrideName),
    [template, overrideName],
  );

  const createMutation = useMutation({
    mutationFn: async () => {
      // 1. Resolve the template server-side (variable_properties, naming,
      //    inheritance) and bump usage_count.
      const resolved = await templatesApi.instantiate(template.template_id, {
        override_name: overrideName.trim() || undefined,
        provide_context: context.trim() || undefined,
      });
      // 2. Chain into LLM elaboration (existing flow) with the resolved name
      //    and any LLM-hint variables folded into the concept.
      const hints = Object.values(resolved.llm_hints);
      const concept = [resolved.description, context.trim(), ...hints]
        .filter(Boolean)
        .join(" — ");
      const generated = await entitiesApi.generateEntity({
        universe_id: resolved.universe_id,
        name: resolved.name,
        concept,
        state_tags: resolved.state_tags,
        save: true,
      });
      return { resolved, generated };
    },
    onSuccess: ({ generated }: any) => {
      setStep("done");
      // usage_count changed server-side
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      if (onCreated && generated?.saved?.entity_id) {
        onCreated(generated.saved.entity_id);
      } else {
        onCreated?.("");
      }
    },
    onError: () => {
      setStep("configure");
    },
  });

  const handleCreate = () => {
    setStep("creating");
    createMutation.mutate();
  };

  const handleClose = () => {
    setStep("configure");
    setOverrideName("");
    setContext("");
    onClose();
  };

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        onClick={handleClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 12 }}
          className="glass-dark rounded-2xl border border-white/10 w-full max-w-md mx-4 overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              <h2 className="text-sm font-semibold text-slate-200">Instantiate Template</h2>
            </div>
            <button onClick={handleClose} aria-label="Close" className="text-slate-500 hover:text-slate-300 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Content */}
          <div className="px-5 py-4 space-y-4 max-h-[70vh] overflow-y-auto">
            {step === "configure" && (
              <>
                {/* Template info */}
                <div className="glass-dark rounded-xl border border-white/5 p-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-200">{template.name}</span>
                    <span className="text-[10px] bg-cyan-500/10 text-cyan-400 px-1.5 py-0.5 rounded border border-cyan-500/20">
                      {template.entity_type}
                    </span>
                  </div>
                  {template.description && (
                    <p className="text-[11px] text-slate-500 leading-relaxed">{template.description}</p>
                  )}
                </div>

                {/* Override name */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold tracking-widest uppercase text-slate-500">
                    Name Override
                  </label>
                  <input
                    value={overrideName}
                    onChange={(e) => setOverrideName(e.target.value)}
                    placeholder={template.naming_pattern.type === "user" ? "Enter a name..." : preview.name}
                    className="input-cyber py-1.5 text-xs w-full"
                  />
                  <p className="text-[10px] text-slate-600">
                    Naming strategy: <span className="text-slate-400">{template.naming_pattern.type}</span>
                    {" · "}will be named <span className="text-cyan-400">{preview.name}</span>
                  </p>
                </div>

                {/* Context hint */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold tracking-widest uppercase text-slate-500">
                    Context Hint
                  </label>
                  <textarea
                    value={context}
                    onChange={(e) => setContext(e.target.value)}
                    placeholder="e.g., 'a nervous innkeeper who suspects the party'"
                    className="input-cyber py-1.5 text-xs w-full resize-none h-16"
                  />
                </div>

                {/* Variable properties preview */}
                {preview.variables.length > 0 && (
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold tracking-widest uppercase text-amber-400 flex items-center gap-1">
                      <Dices className="w-3 h-3" /> Preview — Will Be Generated
                    </label>
                    <div className="space-y-1">
                      {preview.variables.map((pv, i) => (
                        <div key={i} className="flex items-center justify-between text-xs glass-dark rounded-lg border border-white/5 px-2.5 py-1.5">
                          <span className="text-slate-300 font-mono">{pv.property_path}</span>
                          {pv.value !== null ? (
                            <span className="text-[10px] text-cyan-300 font-mono bg-cyan-500/10 px-1.5 py-0.5 rounded">
                              {String(pv.value)}
                            </span>
                          ) : (
                            <span className="text-[10px] text-slate-500 bg-white/5 px-1.5 py-0.5 rounded">
                              {pv.note ?? pv.generation_type}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                    <p className="text-[10px] text-slate-600">
                      Random values re-roll on the server at creation time.
                    </p>
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2 pt-2">
                  <button onClick={handleClose} className="btn-ghost text-xs py-2 flex-1">
                    Cancel
                  </button>
                  <button onClick={handleCreate} className="btn-cyber text-xs py-2 flex-1">
                    <Sparkles className="w-3.5 h-3.5" /> Create Entity
                  </button>
                </div>
              </>
            )}

            {step === "creating" && (
              <div className="flex flex-col items-center justify-center py-8 space-y-3">
                <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
                <p className="text-xs text-slate-400">Creating entity from template...</p>
              </div>
            )}

            {step === "done" && (
              <div className="flex flex-col items-center justify-center py-8 space-y-3">
                <div className="w-10 h-10 rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center">
                  <Check className="w-5 h-5 text-emerald-400" />
                </div>
                <p className="text-xs text-emerald-400 font-medium">Entity created successfully!</p>
                <button onClick={handleClose} className="btn-cyber text-xs py-1.5 px-4 mt-2">
                  Done
                </button>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
