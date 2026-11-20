"use client";

// LLM provider management, extracted from app/config/page.tsx (UX-3) so the
// admin Providers tab and the Configuration page render the same component.

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  Cpu,
  Copy,
  Eye,
  EyeOff,
  FlaskConical,
  Loader2,
  Plus,
  RefreshCw,
  Star,
  Trash2,
  Wifi,
  WifiOff,
  X,
  Zap,
} from "lucide-react";
import { llmApi } from "@/lib/api";
import { SETTINGS_KEYS } from "@/lib/query-keys";
import { useLLMProviders } from "@/hooks/use-llm";
import type { LLMConnection, LLMProvider } from "@/lib/types";
import { cn } from "@/lib/utils";

// ═══════════════════════════════════════════════════════════════
//  LLM TAB
// ═══════════════════════════════════════════════════════════════

export const PROVIDER_META: Record<
  string,
  { label: string; color: string; border: string; bg: string }
> = {
  anthropic: { label: "Anthropic", color: "text-amber-300", border: "border-amber-500/25", bg: "bg-amber-500/8" },
  openai: { label: "OpenAI", color: "text-emerald-300", border: "border-emerald-500/25", bg: "bg-emerald-500/8" },
  github_models: { label: "GitHub Models", color: "text-slate-200", border: "border-slate-500/25", bg: "bg-slate-500/8" },
  ollama: { label: "Ollama", color: "text-purple-300", border: "border-purple-500/25", bg: "bg-purple-500/8" },
  google_ai_studio: { label: "Google AI Studio", color: "text-cyan-300", border: "border-cyan-500/25", bg: "bg-cyan-500/8" },
  groq: { label: "Groq", color: "text-orange-300", border: "border-orange-500/25", bg: "bg-orange-500/8" },
  openrouter: { label: "OpenRouter", color: "text-violet-300", border: "border-violet-500/25", bg: "bg-violet-500/8" },
  z_ai: { label: "Z.AI (ZhipuAI)", color: "text-blue-300", border: "border-blue-500/25", bg: "bg-blue-500/8" },
  minimax: { label: "MiniMax (Anthropic-compatible)", color: "text-teal-300", border: "border-teal-500/25", bg: "bg-teal-500/8" },
  custom: { label: "OpenAI Compatible", color: "text-pink-300", border: "border-pink-500/25", bg: "bg-pink-500/8" },
};

const PROVIDERS: LLMProvider[] = ["anthropic", "openai", "github_models", "google_ai_studio", "ollama", "groq", "openrouter", "z_ai", "minimax", "custom"];

function AddProviderForm({
  onClose,
  availableModels,
  modelsLoading,
  modelError,
  onRefreshModels,
}: {
  onClose: () => void;
  availableModels: (provider: string) => string[];
  modelsLoading: boolean;
  modelError?: (provider: string) => string | undefined;
  onRefreshModels?: (provider: string) => Promise<void>;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: "",
    provider: "anthropic" as LLMProvider,
    model: "",
    api_key: "",
    base_url: "",
    is_default: false,
    role: "standard" as "light" | "standard" | "heavy" | "embedding" | "image" | "transcription",
  });

  const models = availableModels(form.provider);
  const error = modelError?.(form.provider);
  const needsBaseUrl = form.provider === "ollama" || form.provider === "custom" || form.provider === "minimax";

  const add = useMutation({
    mutationFn: () => llmApi.addProvider(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SETTINGS_KEYS.providers });
      onClose();
    },
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      className="glass rounded-2xl border border-cyan-500/20 p-6 space-y-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-cyan-300">Add LLM Provider</h3>
        <button onClick={onClose} aria-label="Close" className="text-slate-600 hover:text-slate-300">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="text-xs text-slate-500">Provider</label>
          <select
            value={form.provider}
            onChange={(e) => setForm({ ...form, provider: e.target.value as LLMProvider, model: "" })}
            className="input-cyber w-full"
          >
            {PROVIDERS.map((p) => {
              const m = PROVIDER_META[p];
              return (
                <option key={p} value={p}>
                  {m?.label ?? p}
                </option>
              );
            })}
          </select>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs text-slate-500">Display name</label>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="My Production LLM"
            className="input-cyber"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs text-slate-500 flex items-center gap-1.5">
            Model
            {modelsLoading && <Loader2 className="w-2.5 h-2.5 animate-spin text-slate-600" />}
          </label>
          <div className="flex gap-2">
            <input
              list={`model-suggestions-${form.provider}`}
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              placeholder={modelsLoading ? "Loading models…" : "Type or pick a model…"}
              className="input-cyber flex-1"
            />
            <button
              type="button"
              onClick={() => onRefreshModels?.(form.provider)}
              disabled={modelsLoading}
              className="btn-ghost px-2"
              title="Refresh models for this provider"
            >
              <RefreshCw className={cn("w-4 h-4", modelsLoading && "animate-spin")} />
            </button>
          </div>
          <datalist id={`model-suggestions-${form.provider}`}>
            {models.map((m) => <option key={m} value={m} />)}
          </datalist>
          {error && (
            <div className="text-xs text-red-400 flex items-center gap-1.5 mt-1">
              <AlertTriangle className="w-3 h-3 flex-shrink-0" />
              {error}
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <label className="text-xs text-slate-500">
            {needsBaseUrl ? "Base URL" : "API Key"}
          </label>
          {needsBaseUrl ? (
            <input
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value })}
              placeholder={form.provider === "ollama" ? "http://localhost:11434" : "https://api.example.com/v1"}
              className="input-cyber"
            />
          ) : (
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              placeholder="sk-…"
              className="input-cyber font-mono"
            />
          )}
        </div>

        {needsBaseUrl && (
          <div className="space-y-1.5">
            <label className="text-xs text-slate-500">API Key</label>
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              placeholder="sk-…"
              className="input-cyber font-mono"
            />
          </div>
        )}

        <div className="space-y-1.5">
          <label className="text-xs text-slate-500">Role tier</label>
          <select
            value={form.role}
            onChange={(e) =>
              setForm({
                ...form,
                role: e.target.value as
                  | "light"
                  | "standard"
                  | "heavy"
                  | "embedding"
                  | "image"
                  | "transcription",
              })
            }
            className="input-cyber"
            aria-label="Role tier"
          >
            <option value="light">Light — fast/cheap tasks</option>
            <option value="standard">Standard — balanced</option>
            <option value="heavy">Heavy — most capable</option>
            <option value="embedding">Embedding — vector embeddings</option>
            <option value="image">Image — image generation</option>
            <option value="transcription">Transcription — speech to text</option>
          </select>
        </div>
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-white/5">
        <label className="flex items-center gap-2 cursor-pointer">
          <div
            onClick={() => setForm({ ...form, is_default: !form.is_default })}
            className={cn(
              "w-8 h-4 rounded-full transition-all relative",
              form.is_default ? "bg-cyan-500" : "bg-white/10",
            )}
          >
            <div
              className={cn(
                "absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all",
                form.is_default ? "left-4.5" : "left-0.5",
              )}
            />
          </div>
          <span className="text-xs text-slate-400">Set as default</span>
        </label>
        <div className="flex gap-3">
          <button onClick={onClose} className="btn-ghost text-xs">Cancel</button>
          <button
            disabled={!form.name || !form.model.trim() || add.isPending}
            onClick={() => add.mutate()}
            className="btn-cyber text-xs"
          >
            {add.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            Add Provider
          </button>
        </div>
      </div>

      {add.isError && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-400 flex items-center gap-2"
        >
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          {(add.error as Error).message}
        </motion.div>
      )}
    </motion.div>
  );
}

const ROLE_COLORS: Record<string, string> = {
  light: "text-sky-300 bg-sky-500/10 border-sky-500/20",
  standard: "text-amber-300 bg-amber-500/10 border-amber-500/20",
  heavy: "text-rose-300 bg-rose-500/10 border-rose-500/20",
  embedding: "text-teal-300 bg-teal-500/10 border-teal-500/20",
  image: "text-fuchsia-300 bg-fuchsia-500/10 border-fuchsia-500/20",
};

function ProviderCard({ conn, models }: { conn: LLMConnection; models: string[] }) {
  const qc = useQueryClient();
  const [showKey, setShowKey] = useState(false);
  const [editModel, setEditModel] = useState(false);
  const [selectedModel, setSelectedModel] = useState(conn.model);
  const [editRole, setEditRole] = useState(false);
  const [selectedRole, setSelectedRole] = useState(conn.role ?? "standard");
  const meta = PROVIDER_META[conn.provider] ?? PROVIDER_META.anthropic;

  const test = useMutation({
    mutationFn: () => llmApi.testProvider(conn.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.providers }),
  });

  const del = useMutation({
    mutationFn: () => llmApi.deleteProvider(conn.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.providers }),
  });

  const dup = useMutation({
    mutationFn: () => llmApi.duplicateProvider(conn.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.providers }),
  });

  const updateModel = useMutation({
    mutationFn: (newModel: string) => llmApi.updateProvider(conn.id, { model: newModel }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SETTINGS_KEYS.providers });
      setEditModel(false);
    },
  });

  const updateRole = useMutation({
    mutationFn: (newRole: string) => llmApi.updateProvider(conn.id, { role: newRole }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SETTINGS_KEYS.providers });
      setEditRole(false);
    },
  });

  const setDefault = useMutation({
    mutationFn: () => llmApi.updateProvider(conn.id, { is_default: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.providers }),
  });

  const isOnline = conn.status === "connected";
  const isError = conn.status === "error";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "glass rounded-2xl border p-5 space-y-4 transition-all duration-200",
        isOnline ? `${meta.border} ${meta.bg}` : "border-white/5",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className={cn("w-10 h-10 rounded-xl border flex items-center justify-center flex-shrink-0", meta.bg, meta.border)}>
            <Cpu className={cn("w-5 h-5", meta.color)} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-slate-100">{conn.name}</h3>
              {conn.is_default
                ? <span title="Default provider"><Star className="w-3 h-3 text-amber-400 fill-amber-400" /></span>
                : <button
                    onClick={() => setDefault.mutate()}
                    disabled={setDefault.isPending}
                    title="Set as default provider"
                    className="p-0 text-slate-600 hover:text-amber-400 transition-colors disabled:opacity-40"
                  >
                    {setDefault.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Star className="w-3 h-3" />}
                  </button>
              }
            </div>
            <p className={cn("text-xs", meta.color)}>{meta.label}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className={cn("flex items-center gap-1.5 text-xs px-2 py-1 rounded-full",
            isOnline ? "text-emerald-300 bg-emerald-500/8" :
            isError ? "text-red-300 bg-red-500/8" :
            "text-slate-500 bg-white/4"
          )}>
            {isOnline ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {conn.status}
            {conn.latency_ms && isOnline && (
              <span className="opacity-60">{Math.round(conn.latency_ms)}ms</span>
            )}
          </div>
          <button onClick={() => dup.mutate()} title="Duplicate" className="p-1.5 rounded hover:text-cyan-400 text-slate-600 transition-all">
            <Copy className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => del.mutate()} className="p-1.5 rounded hover:text-red-400 text-slate-600 transition-all">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Role tier */}
      <div className="space-y-1.5">
        <p className="text-[10px] font-medium text-slate-600 uppercase tracking-wide flex items-center justify-between">
          Role
          {updateRole.isPending && <Loader2 className="w-2.5 h-2.5 animate-spin text-cyan-500" />}
        </p>
        {editRole ? (
          <div className="flex gap-2">
            <select
              value={selectedRole}
              autoFocus
              disabled={updateRole.isPending}
              onChange={(e) => {
                const val = e.target.value as any;
                setSelectedRole(val);
                updateRole.mutate(val);
              }}
              onBlur={() => !updateRole.isPending && setEditRole(false)}
              className="input-cyber flex-1 text-xs"
            >
              <option value="light">Light — fast/cheap tasks</option>
              <option value="standard">Standard — balanced</option>
              <option value="heavy">Heavy — most capable</option>
              <option value="embedding">Embedding — vector embeddings</option>
              <option value="image">Image — image generation</option>
              <option value="transcription">Transcription — speech to text</option>
            </select>
          </div>
        ) : (
          <button
            onClick={() => setEditRole(true)}
            className={cn(
              "flex items-center gap-2 text-xs font-mono px-2 py-1 rounded-md border transition-colors w-full sm:w-auto",
              ROLE_COLORS[conn.role ?? "standard"],
              updateRole.isPending && "opacity-50 cursor-not-allowed"
            )}
          >
            {conn.role ?? "standard"}
            <ChevronDown className="w-3 h-3 opacity-50" />
          </button>
        )}
        {updateRole.isError && (
          <p className="text-[10px] text-red-400 mt-1">Failed to update role</p>
        )}
      </div>

      <div className="space-y-1.5">
        <p className="text-[10px] font-medium text-slate-600 uppercase tracking-wide flex items-center justify-between">
          Model
          {updateModel.isPending && <Loader2 className="w-2.5 h-2.5 animate-spin text-cyan-500" />}
        </p>
        {editModel ? (
          <div className="flex gap-2">
            <select
              value={selectedModel}
              autoFocus
              disabled={updateModel.isPending}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedModel(val);
                updateModel.mutate(val);
              }}
              onBlur={() => !updateModel.isPending && setEditModel(false)}
              className="input-cyber flex-1 text-xs"
            >
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        ) : (
          <button
            onClick={() => setEditModel(true)}
            className={cn(
              "flex items-center gap-2 text-sm font-mono text-slate-300 hover:text-cyan-300 transition-colors w-full text-left",
              updateModel.isPending && "opacity-50 cursor-not-allowed"
            )}
          >
            <span className="truncate">{conn.model}</span>
            <ChevronDown className="w-3 h-3 text-slate-600 flex-shrink-0" />
          </button>
        )}
        {updateModel.isError && (
          <p className="text-[10px] text-red-400 mt-1">Failed to update model</p>
        )}
      </div>

      {conn.api_key_masked && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-medium text-slate-600 uppercase tracking-wide">API Key</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs font-mono text-slate-400 bg-white/4 px-3 py-1.5 rounded-lg">
              {showKey ? conn.api_key_masked : "••••••••••••••••"}
            </code>
            <button
              onClick={() => setShowKey(!showKey)}
              className="p-1.5 text-slate-600 hover:text-slate-300 transition-colors"
            >
              {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>
      )}

      {test.data && (
        <div className={cn("text-xs px-3 py-2 rounded-lg",
          test.data.ok ? "text-emerald-300 bg-emerald-500/8" : "text-red-300 bg-red-500/8"
        )}>
          {test.data.ok
            ? `✓ Connected · ${Math.round(test.data.latency_ms ?? 0)}ms`
            : `✗ ${test.data.error}`}
        </div>
      )}

      <button
        onClick={() => test.mutate()}
        disabled={test.isPending}
        className="w-full btn-cyber justify-center text-xs"
      >
        {test.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wifi className="w-3.5 h-3.5" />}
        Test Connection
      </button>
    </motion.div>
  );
}

const TIER_META: Record<string, { label: string; desc: string; colors: string }> = {
  heavy:    { label: "Heavy",    desc: "Complex reasoning, narration, canon decisions",  colors: "text-rose-300 bg-rose-500/10 border-rose-500/25" },
  standard: { label: "Standard", desc: "Balanced tasks, NPC dialogue, world queries",    colors: "text-amber-300 bg-amber-500/10 border-amber-500/25" },
  light:    { label: "Light",    desc: "Fast/cheap tasks: intent parsing, context prep",  colors: "text-sky-300 bg-sky-500/10 border-sky-500/25" },
  image:    { label: "Image",    desc: "Portraits & scene illustrations",                 colors: "text-fuchsia-300 bg-fuchsia-500/10 border-fuchsia-500/25" },
};

function TierAssignment({ providers }: { providers: LLMConnection[] }) {
  const qc = useQueryClient();

  const assign = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) =>
      llmApi.updateProvider(id, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.providers }),
  });

  const primaryFor = (tier: string) =>
    providers.find((p) => p.role === tier && p.status === "connected" && p.is_default) ??
    providers.find((p) => p.role === tier && p.status === "connected") ??
    providers.find((p) => p.role === tier);

  return (
    <div className="glass rounded-xl border border-white/8 divide-y divide-white/5">
      <div className="px-4 py-2.5 flex items-center gap-2 bg-white/2">
        <Zap className="w-3.5 h-3.5 text-slate-500" />
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Tier Assignment</p>
        <span className="text-xs text-slate-600 ml-1">— primary provider for each task complexity</span>
      </div>
      {(["heavy", "standard", "light", "image"] as const).map((tier) => {
        const meta = TIER_META[tier];
        const current = primaryFor(tier);
        const othersCount = providers.filter(p => p.role === tier && p.id !== current?.id).length;

        return (
          <div key={tier} className="flex items-center gap-3 px-4 py-3 hover:bg-white/2 transition-colors">
            <div className={cn("text-[10px] font-semibold px-2 py-1 rounded border w-18 text-center flex-shrink-0", meta.colors)}>
              {meta.label}
            </div>
            <div className="flex-1 min-w-0">
              <select
                value={current?.id ?? ""}
                disabled={assign.isPending}
                onChange={(e) => { 
                  if (e.target.value) {
                    assign.mutate({ id: e.target.value, role: tier });
                  }
                }}
                className={cn(
                  "input-cyber w-full text-xs",
                  assign.isPending && "opacity-50"
                )}
              >
                <option value="">— unassigned —</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.model}) {p.role === tier ? "✓" : ""}
                  </option>
                ))}
              </select>
              {othersCount > 0 && (
                <p className="text-[9px] text-slate-600 mt-1 ml-1">
                  {othersCount} other {othersCount === 1 ? 'provider' : 'providers'} also tagged as {tier}
                </p>
              )}
            </div>
            <p className="text-[10px] text-slate-600 hidden lg:block w-52 flex-shrink-0 leading-tight">{meta.desc}</p>
          </div>
        );
      })}
    </div>
  );
}

export function LLMProvidersPanel() {
  const [adding, setAdding] = useState(false);
  const qc = useQueryClient();
  const { data: providers = [], isLoading } = useLLMProviders();

  // Per-provider model state management
  const [modelCache, setModelCache] = useState<Record<string, string[]>>({});
  const [modelErrors, setModelErrors] = useState<Record<string, string>>({});
  const [loadingProviders, setLoadingProviders] = useState<Record<string, boolean>>({});

  const [testingAll, setTestingAll] = useState(false);
  const testAll = async () => {
    if (testingAll || providers.length === 0) return;
    setTestingAll(true);
    try {
      await Promise.allSettled(providers.map((p) => llmApi.testProvider(p.id)));
    } finally {
      setTestingAll(false);
      qc.invalidateQueries({ queryKey: SETTINGS_KEYS.providers });
    }
  };

  const fetchModels = async (provider: string, force = false) => {
    if (!force && modelCache[provider]) return;
    
    setLoadingProviders(prev => ({ ...prev, [provider]: true }));
    try {
      const models = await llmApi.listModels(provider);
      setModelCache(prev => ({ ...prev, [provider]: models }));
      setModelErrors(prev => ({ ...prev, [provider]: "" }));
    } catch (error) {
      console.error(`Failed to load models for ${provider}:`, error);
      setModelErrors(prev => ({ ...prev, [provider]: error instanceof Error ? error.message : "Failed to load models" }));
    } finally {
      setLoadingProviders(prev => ({ ...prev, [provider]: false }));
    }
  };

  // Pre-fetch models for existing providers
  useEffect(() => {
    const activeProviders = Array.from(new Set(providers.map(p => p.provider)));
    activeProviders.forEach(p => fetchModels(p));
  }, [providers]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-3">
            LLM Providers
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-slate-500 font-mono">
              {providers.length}
            </span>
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Configure and test LLM connections used by MONITOR agents.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              const activeProviders = Array.from(new Set(providers.map(p => p.provider)));
              activeProviders.forEach(p => fetchModels(p, true));
            }}
            disabled={Object.values(loadingProviders).some(Boolean)}
            className="btn-ghost text-xs"
            title="Refresh all models"
          >
            <RefreshCw className={cn("w-4 h-4", Object.values(loadingProviders).some(Boolean) && "animate-spin")} />
          </button>
          <button
            onClick={testAll}
            disabled={testingAll || providers.length === 0}
            className="btn-ghost text-xs gap-1.5"
            title="Test every configured provider"
          >
            {testingAll ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FlaskConical className="w-4 h-4" />
            )}
            {testingAll ? "Testing…" : "Test All"}
          </button>
          <button onClick={() => setAdding(true)} className="btn-cyber">
            <Plus className="w-4 h-4" /> Add Provider
          </button>
        </div>
      </div>

      <AnimatePresence>
        {adding && (
          <div className="relative">
            <div className="absolute inset-0 bg-cyan-500/5 blur-3xl -z-10" />
            <AddProviderForm
              onClose={() => setAdding(false)}
              availableModels={(p) => modelCache[p] ?? []}
              modelsLoading={Object.values(loadingProviders).some(Boolean)}
              modelError={(p) => modelErrors[p]}
              onRefreshModels={(p) => fetchModels(p, true)}
            />
          </div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-8 items-start">
        <div className="space-y-6">
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="glass h-48 animate-pulse rounded-2xl border border-white/5" />
              ))}
            </div>
          ) : providers.length === 0 ? (
            <div className="glass rounded-2xl border border-dashed border-white/10 p-12 flex flex-col items-center justify-center text-center space-y-3">
              <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center">
                <Cpu className="w-6 h-6 text-slate-600" />
              </div>
              <p className="text-slate-400 font-medium">No LLM providers configured yet.</p>
              <button onClick={() => setAdding(true)} className="text-cyan-400 text-sm hover:underline">
                Add your first provider
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {providers.map((p) => (
                <ProviderCard
                  key={p.id}
                  conn={p}
                  models={modelCache[p.provider] ?? []}
                />
              ))}
            </div>
          )}
        </div>

        <div className="space-y-6">
          <TierAssignment providers={providers} />
          
          <div className="glass rounded-xl border border-amber-500/10 bg-amber-500/5 p-4 space-y-2">
            <div className="flex items-center gap-2 text-amber-300">
              <AlertCircle className="w-3.5 h-3.5" />
              <p className="text-[10px] font-bold uppercase tracking-wider">How assignments work</p>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              MONITOR agents use the <strong>Role Tier</strong> to pick a model. If multiple providers share a role,
              the system prioritizes those marked as <strong>Default</strong>, then those with the fastest <strong>Latency</strong>.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
