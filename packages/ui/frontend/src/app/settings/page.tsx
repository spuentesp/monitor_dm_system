"use client";

import { StatusDot } from "@/components/StatusDot";
import { chatApi, dbApi, llmApi, performanceApi, promptsApi } from "@/lib/api";
import { SETTINGS_KEYS, PLAY_KEYS, BENCHMARK_KEYS } from "@/lib/query-keys";
import { useLLMProviders, useLLMAssignments } from "@/hooks/use-llm";
import { useDatabases } from "@/hooks/use-databases";
import type {
    ChatSessionState,
    DatabaseStatus,
    LLMConnection,
    LLMProvider,
    Message,
    NodeAssignment,
    PlaytestBenchmark,
    PromptModuleDetail,
    PromptModuleSummary,
    PromptTestResult,
    Session,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
    Activity,
    AlertCircle,
    AlertTriangle,
    Bot,
    Check,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    Code2,
    Copy,
    Cpu,
    Database,
    Eye,
    EyeOff,
    FlaskConical,
    Layers,
    Loader2,
    Network,
    Pencil,
    Plus,
    RefreshCw,
    RotateCcw,
    Server,
    Settings,
    Sparkles,
    Star,
    Terminal,
    Trash2,
    Wifi,
    WifiOff,
    X,
    Zap,
    Gauge,
    Palette
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

// ─── Tab definitions ───────────────────────────────────────────

const SETTINGS_TABS = [
  { id: "llm", label: "LLM Providers", icon: Cpu },
  { id: "agents", label: "Agents", icon: Network },
  { id: "testbed", label: "Benchmark Testbed", icon: FlaskConical },
  { id: "databases", label: "Databases", icon: Database },
  { id: "tone", label: "Tone", icon: Palette },
  { id: "performance", label: "Performance", icon: Gauge },
] as const;

type SettingsTab = (typeof SETTINGS_TABS)[number]["id"];

// ═══════════════════════════════════════════════════════════════
//  LLM TAB
// ═══════════════════════════════════════════════════════════════

const PROVIDER_META: Record<
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
    role: "standard" as "light" | "standard" | "heavy" | "embedding",
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
            onChange={(e) => setForm({ ...form, role: e.target.value as "light" | "standard" | "heavy" | "embedding" })}
            className="input-cyber"
          >
            <option value="light">Light — fast/cheap tasks</option>
            <option value="standard">Standard — balanced</option>
            <option value="heavy">Heavy — most capable</option>
            <option value="embedding">Embedding — vector embeddings</option>
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
      {(["heavy", "standard", "light"] as const).map((tier) => {
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

function LLMTab() {
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

function BenchmarkTestbedTab() {
  const router = useRouter();
  const qc = useQueryClient();
  const [selectedBenchmarkId, setSelectedBenchmarkId] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState("");

  const { data: benchmarks = [], isLoading: benchmarksLoading } = useQuery<PlaytestBenchmark[]>({
    queryKey: PLAY_KEYS.benchmarks,
    queryFn: chatApi.listBenchmarks,
  });

  const { data: benchmarkSessions = [], isLoading: sessionsLoading } = useQuery<Session[]>({
    queryKey: BENCHMARK_KEYS.sessions,
    queryFn: async () => {
      const sessions = await chatApi.listSessions();
      return sessions
        .filter((session) => Boolean(session.benchmark_id))
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    },
  });

  useEffect(() => {
    if (!selectedBenchmarkId && benchmarks[0]?.benchmark_id) {
      setSelectedBenchmarkId(benchmarks[0].benchmark_id);
    }
  }, [benchmarks, selectedBenchmarkId]);

  useEffect(() => {
    if (!selectedSessionId && benchmarkSessions[0]?.id) {
      setSelectedSessionId(benchmarkSessions[0].id);
    }
  }, [benchmarkSessions, selectedSessionId]);

  const selectedBenchmark =
    benchmarks.find((item) => item.benchmark_id === selectedBenchmarkId) ?? benchmarks[0] ?? null;

  const selectedSession =
    benchmarkSessions.find((item) => item.id === selectedSessionId) ?? benchmarkSessions[0] ?? null;

  const { data: sessionState, isLoading: stateLoading } = useQuery<ChatSessionState>({
    queryKey: BENCHMARK_KEYS.sessionState(selectedSession?.id),
    queryFn: () => chatApi.getSessionState(selectedSession!.id),
    enabled: !!selectedSession?.id,
  });

  const { data: sessionMessages = [] } = useQuery<Message[]>({
    queryKey: BENCHMARK_KEYS.sessionMessages(selectedSession?.id),
    queryFn: () => chatApi.getMessages(selectedSession!.id),
    enabled: !!selectedSession?.id,
  });

  const launchBenchmark = useMutation({
    mutationFn: (benchmark: PlaytestBenchmark) =>
      chatApi.createSession({
        title: benchmark.session_title ?? `Benchmark: ${benchmark.name}`,
        mode: benchmark.mode,
        tone: benchmark.tone,
        play_mode: benchmark.play_mode,
        system_id: benchmark.resolved_system_id ?? null,
        system_label: benchmark.resolved_system_name ?? benchmark.system_name ?? null,
        benchmark_id: benchmark.benchmark_id,
        benchmark_label: benchmark.name,
      }),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: BENCHMARK_KEYS.sessions });
      qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
      setSelectedSessionId(session.id);
      router.push(`/play?session=${session.id}`);
    },
  });

  const recentMessages = sessionMessages.slice(-4);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100">Benchmark Testbed</h2>
          <p className="text-sm text-slate-500 mt-1 max-w-3xl">
            Run MONITOR app benchmarks from Settings instead of the Play setup. Use this testbed to launch repeatable flows,
            compare outcomes, and inspect the latest run state in one place.
          </p>
        </div>
        <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3 text-xs text-cyan-100">
          <div className="font-medium text-cyan-300">Configured benchmarks</div>
          <div className="mt-1 text-lg font-semibold text-slate-100">{benchmarks.length}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_0.8fr] gap-5">
        <div className="glass rounded-2xl border border-cyan-500/15 p-5 space-y-4">
          <div className="flex items-center gap-2 text-slate-200">
            <FlaskConical className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold">Launch benchmark</h3>
          </div>

          {benchmarksLoading ? (
            <div className="flex items-center gap-2 text-slate-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading benchmark catalog…
            </div>
          ) : benchmarks.length === 0 ? (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-200">
              No benchmark flows are configured yet.
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <label className="text-[10px] text-slate-600 uppercase tracking-wide">Benchmark flow</label>
                <select
                  value={selectedBenchmark?.benchmark_id ?? ""}
                  onChange={(e) => setSelectedBenchmarkId(e.target.value)}
                  className="input-cyber w-full"
                >
                  {benchmarks.map((benchmark) => (
                    <option key={benchmark.benchmark_id} value={benchmark.benchmark_id}>
                      {benchmark.name}
                    </option>
                  ))}
                </select>
              </div>

              {selectedBenchmark && (
                <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-xs text-slate-300 space-y-2">
                  <div className="font-medium text-amber-300">{selectedBenchmark.name}</div>
                  <p className="text-slate-400 leading-relaxed">{selectedBenchmark.description}</p>
                  <div><span className="text-slate-300">System:</span> {selectedBenchmark.resolved_system_name ?? selectedBenchmark.system_name ?? "Not resolved"}</div>
                  <div><span className="text-slate-300">Mode:</span> {selectedBenchmark.mode} · {selectedBenchmark.play_mode}</div>
                  <div><span className="text-slate-300">Scripted turns:</span> {selectedBenchmark.scripted_turn_count}</div>
                  {selectedBenchmark.focus_areas.length > 0 && (
                    <div><span className="text-slate-300">Focus:</span> {selectedBenchmark.focus_areas.slice(0, 3).join(" · ")}</div>
                  )}
                  {selectedBenchmark.comparison_metrics.length > 0 && (
                    <div><span className="text-slate-300">Metrics:</span> {selectedBenchmark.comparison_metrics.slice(0, 3).join(" / ")}</div>
                  )}
                  {selectedBenchmark.ui_notes && (
                    <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-2.5 py-2 text-cyan-100">
                      <span className="text-cyan-300 font-medium">UI note:</span> {selectedBenchmark.ui_notes}
                    </div>
                  )}
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => selectedBenchmark && launchBenchmark.mutate(selectedBenchmark)}
                  disabled={!selectedBenchmark || launchBenchmark.isPending}
                  className="btn-cyber"
                >
                  {launchBenchmark.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <FlaskConical className="w-4 h-4" />}
                  Run benchmark in Play
                </button>
                {selectedSession && (
                  <button
                    onClick={() => router.push(`/play?session=${selectedSession.id}`)}
                    className="btn-ghost"
                  >
                    <ChevronRight className="w-4 h-4" /> Open latest run
                  </button>
                )}
              </div>

              <p className="text-[10px] text-slate-600 leading-relaxed">
                Benchmarks are now launched from Settings so the app testbed stays with the rest of configuration and diagnostics.
              </p>
            </>
          )}
        </div>

        <div className="glass rounded-2xl border border-white/5 p-5 space-y-4">
          <div className="flex items-center gap-2 text-slate-200">
            <Activity className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-semibold">Recent benchmark runs</h3>
          </div>

          {sessionsLoading ? (
            <div className="flex items-center gap-2 text-slate-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading runs…
            </div>
          ) : benchmarkSessions.length === 0 ? (
            <div className="rounded-xl border border-white/5 bg-white/5 px-4 py-3 text-sm text-slate-500">
              No benchmark sessions yet. Launch one from the testbed to start tracking results.
            </div>
          ) : (
            <div className="space-y-2 max-h-[24rem] overflow-y-auto pr-1">
              {benchmarkSessions.slice(0, 8).map((session) => (
                <button
                  key={session.id}
                  onClick={() => setSelectedSessionId(session.id)}
                  className={cn(
                    "w-full text-left rounded-xl border px-3 py-2 transition-all",
                    selectedSession?.id === session.id
                      ? "border-cyan-500/30 bg-cyan-500/10"
                      : "border-white/5 bg-white/5 hover:border-white/10 hover:bg-white/7",
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-200 truncate">{session.title}</div>
                      <div className="text-[11px] text-slate-500 mt-1">
                        {session.benchmark_label ?? "Benchmark run"} · {session.system_label ?? "No system"}
                      </div>
                    </div>
                    <span className="text-[10px] text-slate-600 whitespace-nowrap">{session.message_count} msgs</span>
                  </div>
                  <div className="text-[10px] text-slate-600 mt-1">Updated {new Date(session.updated_at).toLocaleString()}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="glass rounded-2xl border border-white/5 p-5 space-y-4">
        <div className="flex items-center gap-2 text-slate-200">
          <Bot className="w-4 h-4 text-emerald-400" />
          <h3 className="text-sm font-semibold">Benchmark results</h3>
        </div>

        {!selectedSession ? (
          <div className="rounded-xl border border-white/5 bg-white/5 px-4 py-3 text-sm text-slate-500 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 mt-0.5 text-slate-400 flex-shrink-0" />
            Pick a benchmark run to inspect its latest state and transcript.
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div className="rounded-xl border border-white/5 bg-white/5 px-3 py-3">
                <div className="text-slate-500 uppercase tracking-wide text-[10px]">Benchmark</div>
                <div className="text-slate-100 mt-1 font-medium">{selectedSession.benchmark_label ?? "Custom"}</div>
              </div>
              <div className="rounded-xl border border-white/5 bg-white/5 px-3 py-3">
                <div className="text-slate-500 uppercase tracking-wide text-[10px]">Messages</div>
                <div className="text-slate-100 mt-1 font-medium">{selectedSession.message_count}</div>
              </div>
              <div className="rounded-xl border border-white/5 bg-white/5 px-3 py-3">
                <div className="text-slate-500 uppercase tracking-wide text-[10px]">Last update</div>
                <div className="text-slate-100 mt-1 font-medium">{new Date(selectedSession.updated_at).toLocaleString()}</div>
              </div>
            </div>

            {stateLoading ? (
              <div className="flex items-center gap-2 text-slate-500 text-sm">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading result snapshot…
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="rounded-xl border border-cyan-500/15 bg-cyan-500/5 px-4 py-3 text-xs text-slate-300">
                  <div className="font-medium text-cyan-300 mb-2">Recent phase sequence</div>
                  {sessionState?.recent_phase_sequence?.length ? sessionState.recent_phase_sequence.join(" → ") : "No turn phases recorded yet."}
                </div>
                <div className="rounded-xl border border-purple-500/15 bg-purple-500/5 px-4 py-3 text-xs text-slate-300">
                  <div className="font-medium text-purple-300 mb-2">Recent success levels</div>
                  {sessionState?.recent_success_levels?.length ? sessionState.recent_success_levels.join(" · ") : "No mechanical outcomes yet."}
                </div>
              </div>
            )}

            <div className="rounded-xl border border-white/5 bg-white/5 px-4 py-3 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-medium text-slate-200">Latest transcript</div>
                <button onClick={() => router.push(`/play?session=${selectedSession.id}`)} className="btn-ghost py-1 px-2 text-xs">
                  <ChevronRight className="w-3.5 h-3.5" /> Open run
                </button>
              </div>

              {recentMessages.length === 0 ? (
                <p className="text-xs text-slate-500">No transcript yet. Send benchmark prompts in the Play console and the results will appear here.</p>
              ) : (
                <div className="space-y-2">
                  {recentMessages.map((message) => (
                    <div key={message.id} className="rounded-lg border border-white/5 bg-black/10 px-3 py-2 text-xs">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="font-medium text-slate-200 uppercase tracking-wide">{message.role}</span>
                        <span className="text-[10px] text-slate-600">{new Date(message.timestamp).toLocaleString()}</span>
                      </div>
                      <p className="text-slate-300 leading-relaxed whitespace-pre-wrap">
                        {message.content || "(streaming / empty message)"}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  DATABASES TAB
// ═══════════════════════════════════════════════════════════════

const DB_META: Record<
  string,
  { label: string; role: string; accent: string; border: string; bg: string }
> = {
  neo4j: { label: "Neo4j", role: "Canonical Graph", accent: "text-cyan-300", border: "border-cyan-500/20", bg: "bg-cyan-500/5" },
  mongodb: { label: "MongoDB", role: "Narrative & Proposals", accent: "text-emerald-300", border: "border-emerald-500/20", bg: "bg-emerald-500/5" },
  qdrant: { label: "Qdrant", role: "Semantic Vectors", accent: "text-purple-300", border: "border-purple-500/20", bg: "bg-purple-500/5" },
  minio: { label: "MinIO", role: "Object Storage", accent: "text-amber-300", border: "border-amber-500/20", bg: "bg-amber-500/5" },
  opensearch: { label: "OpenSearch", role: "Full-Text Search", accent: "text-sky-300", border: "border-sky-500/20", bg: "bg-sky-500/5" },
};

function DBCard({ db }: { db: DatabaseStatus }) {
  const meta = DB_META[db.db_type] ?? {
    label: db.name,
    role: db.db_type,
    accent: "text-slate-300",
    border: "border-white/10",
    bg: "bg-white/2",
  };

  const isOnline = db.status === "online";
  const isOffline = db.status === "offline";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "glass rounded-2xl border p-5 space-y-4 transition-all duration-300",
        isOnline ? `${meta.border} ${meta.bg}` : "border-white/5",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0", meta.bg, "border", meta.border)}>
            <Server className={cn("w-5 h-5", meta.accent)} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">{meta.label}</h3>
            <p className="text-xs text-slate-600">{meta.role}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusDot status={db.status} animate />
          <span className={cn("text-xs font-medium",
            isOnline ? "text-emerald-400" : isOffline ? "text-red-400" : "text-amber-400"
          )}>
            {db.status}
          </span>
        </div>
      </div>

      <div className="text-[10px] font-mono text-slate-600 bg-white/3 rounded-lg px-3 py-2 truncate">
        {db.url}
      </div>

      {db.latency_ms != null && (
        <div className="flex items-center gap-2">
          <Activity className={cn("w-3.5 h-3.5 flex-shrink-0", meta.accent)} />
          <div className="flex-1 stat-bar-track">
            <div
              className={cn("stat-bar-fill", {
                "bg-emerald-500": db.latency_ms < 50,
                "bg-amber-500": db.latency_ms >= 50 && db.latency_ms < 200,
                "bg-red-500": db.latency_ms >= 200,
              })}
              style={{ width: `${Math.min(db.latency_ms / 500 * 100, 100)}%` }}
            />
          </div>
          <span className="text-xs font-mono text-slate-400 flex-shrink-0 w-16 text-right">
            {Math.round(db.latency_ms)}ms
          </span>
        </div>
      )}

      {db.version && (
        <p className="text-[10px] text-slate-600 font-mono">v{db.version}</p>
      )}

      {Object.keys(db.stats).length > 0 && (
        <div className="space-y-2 border-t border-white/5 pt-3">
          {Object.entries(db.stats).slice(0, 6).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between">
              <span className="text-xs text-slate-600 capitalize">{k.replace(/_/g, " ")}</span>
              <span className={cn("text-xs font-mono", meta.accent)}>
                {typeof v === "number" ? v.toLocaleString() : v}
              </span>
            </div>
          ))}
        </div>
      )}

      {db.error && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/5 border border-red-500/15 rounded-lg px-3 py-2">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <span className="break-all">{db.error.slice(0, 120)}</span>
        </div>
      )}
    </motion.div>
  );
}

function DatabasesTab() {
  const { data: dbs = [], isLoading, isFetching, refetch } = useDatabases();

  const online = dbs.filter((d) => d.status === "online").length;
  const offline = dbs.filter((d) => d.status === "offline").length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100">Databases</h2>
          <p className="text-sm text-slate-500 mt-1">
            Real-time health and statistics for all MONITOR data stores.
          </p>
        </div>
        <button onClick={() => refetch()} disabled={isFetching} className="btn-ghost">
          <RefreshCw className={cn("w-4 h-4", isFetching && "animate-spin")} /> Refresh
        </button>
      </div>

      {dbs.length > 0 && (
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <StatusDot status="online" animate />
            <span className="text-sm text-slate-400">
              <span className="text-emerald-400 font-semibold">{online}</span> online
            </span>
          </div>
          {offline > 0 && (
            <div className="flex items-center gap-2">
              <StatusDot status="offline" />
              <span className="text-sm text-slate-400">
                <span className="text-red-400 font-semibold">{offline}</span> offline
              </span>
            </div>
          )}
          <span className="text-xs text-slate-600">Refreshes every 30s</span>
        </div>
      )}

      {isLoading && (
        <div className="flex-1 flex items-center justify-center py-24">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
            <p className="text-sm text-slate-500">Pinging databases…</p>
          </div>
        </div>
      )}

      {!isLoading && dbs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 space-y-3">
          <WifiOff className="w-12 h-12 text-slate-700" />
          <p className="text-slate-500 text-sm">No databases reachable.</p>
          <button onClick={() => refetch()} className="btn-cyber">
            <RefreshCw className="w-4 h-4" /> Retry
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {dbs.map((db, i) => (
          <motion.div key={db.db_type} transition={{ delay: i * 0.05 }}>
            <DBCard db={db} />
          </motion.div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  PROMPT MODULES — components (used inside Agents tab)
// ═══════════════════════════════════════════════════════════════

const PROMPT_AGENT_COLORS: Record<string, { tag: string; icon: string; border: string; bg: string }> = {
  Narrator:        { tag: "tag-purple",  icon: "text-purple-400",  border: "border-purple-500/25",  bg: "bg-purple-500/8"  },
  CanonKeeper:     { tag: "tag-cyan",    icon: "text-cyan-400",    border: "border-cyan-500/25",    bg: "bg-cyan-500/8"    },
  ContextAssembly: { tag: "tag-emerald", icon: "text-emerald-400", border: "border-emerald-500/25", bg: "bg-emerald-500/8" },
  Analyzer:        { tag: "tag-amber",   icon: "text-amber-400",   border: "border-amber-500/25",   bg: "bg-amber-500/8"   },
  NPCVoice:        { tag: "tag-dim",     icon: "text-slate-400",   border: "border-slate-500/25",   bg: "bg-slate-500/8"   },
};

const PROMPT_ROLE_COLORS: Record<string, string> = {
  heavy:    "text-purple-300 bg-purple-500/10 border border-purple-500/20",
  standard: "text-cyan-300   bg-cyan-500/10   border border-cyan-500/20",
  light:    "text-emerald-300 bg-emerald-500/10 border border-emerald-500/20",
};

const PROMPT_PREDICTOR_COLORS: Record<string, string> = {
  ChainOfThought: "text-amber-300 bg-amber-500/10 border border-amber-500/20",
  Predict:        "text-slate-300 bg-slate-500/10 border border-slate-500/20",
};

function promptAgentColors(agent: string) {
  return PROMPT_AGENT_COLORS[agent] ?? PROMPT_AGENT_COLORS["Narrator"];
}

function ModuleList({
  modules,
  selectedId,
  onSelect,
}: {
  modules: PromptModuleSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const groups = modules.reduce<Record<string, PromptModuleSummary[]>>((acc, m) => {
    (acc[m.agent] ??= []).push(m);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {Object.entries(groups).map(([agent, items]) => {
        const colors = promptAgentColors(agent);
        return (
          <div key={agent}>
            <div className={cn("text-[10px] font-bold tracking-widest uppercase px-2 py-1 mb-1", colors.icon)}>
              {agent}
            </div>
            <div className="space-y-1">
              {items.map((m) => (
                <button
                  key={m.module_id}
                  onClick={() => onSelect(m.module_id)}
                  className={cn(
                    "w-full text-left px-3 py-2.5 rounded-xl border transition-all duration-150 group",
                    selectedId === m.module_id
                      ? `${colors.bg} ${colors.border} text-slate-100`
                      : "border-transparent hover:bg-white/4 text-slate-400 hover:text-slate-200",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-xs font-medium truncate">{m.label}</div>
                      <div className="text-[10px] text-slate-600 truncate mt-0.5">
                        {m.llm_node} · {m.predictor_type}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {m.has_override && (
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" title="Has override" />
                      )}
                      <ChevronRight
                        className={cn(
                          "w-3 h-3 transition-colors",
                          selectedId === m.module_id ? colors.icon : "text-slate-700 group-hover:text-slate-500",
                        )}
                      />
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FieldTable({ fields, direction }: { fields: { name: string; desc: string }[]; direction: "in" | "out" }) {
  const color = direction === "in" ? "text-cyan-400" : "text-purple-400";
  const label = direction === "in" ? "Inputs" : "Outputs";
  return (
    <div className="space-y-2">
      <div className={cn("text-[10px] font-bold tracking-widest uppercase", color)}>{label}</div>
      <div className="space-y-2">
        {fields.map((f) => (
          <div key={f.name} className="rounded-lg border border-white/5 bg-white/2 px-3 py-2.5">
            <code className="text-xs font-mono text-slate-200">{f.name}</code>
            <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function PromptTestPanel({ detail }: { detail: PromptModuleDetail }) {
  const [inputs, setInputs] = useState<Record<string, string>>(() =>
    Object.fromEntries(detail.input_fields.map((f) => [f.name, ""])),
  );
  const [useOverride, setUseOverride] = useState(true);
  const [result, setResult] = useState<PromptTestResult | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  const run = useMutation({
    mutationFn: () => promptsApi.test(detail.module_id, inputs, useOverride),
    onSuccess: (r) => setResult(r),
  });

  const filledCount = Object.values(inputs).filter((v) => v.trim()).length;
  const allFilled = filledCount === detail.input_fields.length;

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        {detail.input_fields.map((f) => (
          <div key={f.name} className="space-y-1.5">
            <label className="text-[10px] font-mono text-slate-500">
              {f.name}
              <span className="ml-2 text-slate-700 normal-case font-sans font-normal">
                {f.desc.slice(0, 60)}{f.desc.length > 60 ? "…" : ""}
              </span>
            </label>
            <textarea
              value={inputs[f.name] ?? ""}
              onChange={(e) => setInputs({ ...inputs, [f.name]: e.target.value })}
              rows={2}
              className="input-cyber w-full font-mono text-xs resize-y"
              placeholder={`Enter ${f.name}…`}
            />
          </div>
        ))}
      </div>

      <div className="flex items-center gap-4 text-xs text-slate-500">
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <button
            onClick={() => setUseOverride(!useOverride)}
            className={cn("w-8 h-4 rounded-full transition-colors relative", useOverride ? "bg-amber-500" : "bg-white/10")}
          >
            <span className={cn("absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all", useOverride ? "left-4" : "left-0.5")} />
          </button>
          Use current override instructions
        </label>
      </div>

      <button
        onClick={() => run.mutate()}
        disabled={run.isPending || !allFilled}
        className={cn(
          "flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all",
          allFilled && !run.isPending
            ? "bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/25"
            : "bg-white/4 border border-white/8 text-slate-600 cursor-not-allowed",
        )}
      >
        {run.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FlaskConical className="w-3.5 h-3.5" />}
        {run.isPending ? "Running…" : `Run test${!allFilled ? ` (${filledCount}/${detail.input_fields.length} filled)` : ""}`}
      </button>

      <AnimatePresence>
        {result && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {result.ok ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-400" />
                )}
                <span className={cn("text-xs font-medium", result.ok ? "text-emerald-300" : "text-red-300")}>
                  {result.ok ? "Success" : "Error"}
                </span>
              </div>
              {result.latency_ms != null && (
                <span className="text-[10px] text-slate-600">
                  {result.latency_ms < 1000 ? `${result.latency_ms}ms` : `${(result.latency_ms / 1000).toFixed(1)}s`}
                </span>
              )}
            </div>
            {!result.ok && result.error && (
              <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3">
                <p className="text-xs text-red-300 font-mono whitespace-pre-wrap">{result.error}</p>
              </div>
            )}
            {result.ok && Object.entries(result.outputs).length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] font-bold tracking-widest uppercase text-purple-400">Outputs</div>
                {Object.entries(result.outputs).map(([key, val]) => (
                  <div key={key} className="rounded-xl border border-purple-500/15 bg-purple-500/5 p-3 space-y-1">
                    <code className="text-[10px] font-mono text-purple-400">{key}</code>
                    <p className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed">{val}</p>
                  </div>
                ))}
              </div>
            )}
            {result.raw_prompt && (
              <div>
                <button
                  onClick={() => setShowRaw(!showRaw)}
                  className="flex items-center gap-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
                >
                  <Terminal className="w-3.5 h-3.5" />
                  {showRaw ? "Hide" : "Show"} raw prompt
                </button>
                <AnimatePresence>
                  {showRaw && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="overflow-hidden mt-2"
                    >
                      <div className="rounded-xl border border-white/8 bg-black/30 p-3 max-h-96 overflow-y-auto">
                        <pre className="text-[10px] text-slate-400 whitespace-pre-wrap font-mono leading-relaxed">
                          {result.raw_prompt}
                        </pre>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

type PromptDetailTab = "instructions" | "fields" | "test";

function PromptDetailPanel({ moduleId }: { moduleId: string }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<PromptDetailTab>("instructions");
  const [editingInstructions, setEditingInstructions] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const { data: detail, isLoading } = useQuery({
    queryKey: SETTINGS_KEYS.module(moduleId),
    queryFn: () => promptsApi.getModule(moduleId),
  });

  const saveInstructions = useMutation({
    mutationFn: (instructions: string) => promptsApi.updateInstructions(moduleId, instructions),
    onSuccess: (updated) => {
      qc.setQueryData(SETTINGS_KEYS.module(moduleId), updated);
      qc.invalidateQueries({ queryKey: SETTINGS_KEYS.modules });
      setEditingInstructions(null);
      setSaveMsg(updated.has_override ? "Override saved" : "Reset to default");
      setTimeout(() => setSaveMsg(null), 2500);
    },
  });

  const resetOverride = useMutation({
    mutationFn: () => promptsApi.resetOverride(moduleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SETTINGS_KEYS.module(moduleId) });
      qc.invalidateQueries({ queryKey: SETTINGS_KEYS.modules });
      setEditingInstructions(null);
      setSaveMsg("Reset to default");
      setTimeout(() => setSaveMsg(null), 2500);
    },
  });

  if (isLoading || !detail) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
      </div>
    );
  }

  const colors = promptAgentColors(detail.agent);
  const activeInstructions = editingInstructions ?? detail.current_instructions;
  const isDirty = editingInstructions !== null && editingInstructions !== detail.current_instructions;

  const tabs: { id: PromptDetailTab; icon: React.ReactNode; label: string }[] = [
    { id: "instructions", icon: <Pencil className="w-3.5 h-3.5" />, label: "Instructions" },
    { id: "fields",       icon: <Layers className="w-3.5 h-3.5" />,  label: "Fields" },
    { id: "test",         icon: <FlaskConical className="w-3.5 h-3.5" />, label: "Test" },
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-5 border-b border-white/5 flex-shrink-0">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={cn("text-[10px] font-bold tracking-widest uppercase", colors.icon)}>{detail.agent}</span>
              {detail.has_override && (
                <span className="text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/20 px-1.5 py-0.5 rounded-md">
                  overridden
                </span>
              )}
              {detail.override_updated_at && (
                <span className="text-[10px] text-slate-600">{new Date(detail.override_updated_at).toLocaleDateString()}</span>
              )}
            </div>
            <h2 className="text-base font-semibold text-slate-100">{detail.label}</h2>
            <p className="text-xs text-slate-500 mt-0.5">{detail.description}</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className={cn("text-[10px] px-2 py-0.5 rounded-md font-mono", PROMPT_PREDICTOR_COLORS[detail.predictor_type])}>
              {detail.predictor_type}
            </span>
            <span className={cn("text-[10px] px-2 py-0.5 rounded-md font-mono", PROMPT_ROLE_COLORS[detail.llm_role])}>
              {detail.llm_role}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1 mt-4">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                tab === t.id
                  ? `${colors.bg} ${colors.icon} border ${colors.border}`
                  : "text-slate-500 hover:text-slate-300 hover:bg-white/4",
              )}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5">
        {tab === "instructions" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <div className="text-xs text-slate-400 font-medium">System Instructions</div>
                <div className="text-[10px] text-slate-600">
                  DSPy system prompt injected for this module.
                  {detail.has_override && " Production modules pick up overrides on restart."}
                </div>
              </div>
              {detail.has_override && (
                <button
                  onClick={() => resetOverride.mutate()}
                  disabled={resetOverride.isPending}
                  className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-red-400 transition-colors px-2 py-1 rounded-lg hover:bg-red-500/5"
                >
                  {resetOverride.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                  Reset
                </button>
              )}
            </div>
            <textarea
              value={activeInstructions}
              onChange={(e) => setEditingInstructions(e.target.value)}
              rows={16}
              className="input-cyber w-full font-mono text-xs resize-y leading-relaxed"
              spellCheck={false}
            />
            {detail.has_override && (
              <details className="group">
                <summary className="text-[10px] text-slate-600 cursor-pointer hover:text-slate-400 select-none">
                  View original default
                </summary>
                <div className="mt-2 rounded-xl border border-white/5 bg-black/20 p-3 max-h-40 overflow-y-auto">
                  <pre className="text-[10px] text-slate-600 whitespace-pre-wrap font-mono leading-relaxed">
                    {detail.default_instructions}
                  </pre>
                </div>
              </details>
            )}
            <div className="flex items-center justify-between pt-2 border-t border-white/5">
              <AnimatePresence>
                {saveMsg ? (
                  <motion.span
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    className="text-xs text-emerald-400 flex items-center gap-1.5"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {saveMsg}
                  </motion.span>
                ) : (
                  <span />
                )}
              </AnimatePresence>
              <div className="flex items-center gap-2">
                {isDirty && (
                  <button
                    onClick={() => setEditingInstructions(null)}
                    className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 px-3 py-1.5 rounded-lg hover:bg-white/4 transition-all"
                  >
                    <X className="w-3.5 h-3.5" />
                    Discard
                  </button>
                )}
                <button
                  onClick={() => saveInstructions.mutate(activeInstructions)}
                  disabled={saveInstructions.isPending || !isDirty}
                  className={cn(
                    "flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-xl font-semibold transition-all",
                    isDirty
                      ? "bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/25"
                      : "bg-white/4 border border-white/8 text-slate-600 cursor-not-allowed",
                  )}
                >
                  {saveInstructions.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  Save override
                </button>
              </div>
            </div>
          </div>
        )}
        {tab === "fields" && (
          <div className="space-y-6">
            <div className="text-xs text-slate-500 leading-relaxed">
              DSPy field descriptions guide how the LLM uses each input and formats each output.
            </div>
            <FieldTable fields={detail.input_fields} direction="in" />
            <FieldTable fields={detail.output_fields} direction="out" />
          </div>
        )}
        {tab === "test" && (
          <div className="space-y-4">
            <div className="text-xs text-slate-500 leading-relaxed">
              Runs a real LLM call using the{" "}
              <code className="text-slate-400 font-mono">{detail.llm_node}</code> node (
              {detail.llm_role} model). Token usage will be consumed.
            </div>
            <PromptTestPanel detail={detail} />
          </div>
        )}
      </div>
    </div>
  );
}

function PromptsPanel() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: modules = [], isLoading } = useQuery({
    queryKey: SETTINGS_KEYS.modules,
    queryFn: () => promptsApi.list(),
  });

  return (
    <div className="flex h-[calc(100vh-12rem)] overflow-hidden rounded-xl border border-white/5">
      {/* Left: module list */}
      <div className="w-64 flex-shrink-0 glass border-r border-white/5 flex flex-col overflow-hidden">
        <div className="px-4 py-4 border-b border-white/5 flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-cyan-500/10 border border-cyan-500/25 flex items-center justify-center">
              <Zap className="w-3 h-3 text-cyan-400" />
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-200">Prompt Modules</div>
              <div className="text-[10px] text-slate-600">
                {isLoading ? "Loading…" : `${modules.length} modules`}
              </div>
            </div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-3">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 text-slate-600 animate-spin" />
            </div>
          ) : modules.length === 0 ? (
            <div className="text-xs text-slate-600 text-center py-8 px-3">Agents package not available</div>
          ) : (
            <ModuleList modules={modules} selectedId={selectedId} onSelect={setSelectedId} />
          )}
        </div>
        <div className="px-4 py-3 border-t border-white/5 flex-shrink-0">
          <p className="text-[10px] text-slate-700"><span className="text-amber-400/70">●</span> amber dot = active override</p>
        </div>
      </div>

      {/* Right: detail */}
      <div className="flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          {selectedId ? (
            <motion.div key={selectedId} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="h-full">
              <PromptDetailPanel moduleId={selectedId} />
            </motion.div>
          ) : (
            <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="h-full flex flex-col items-center justify-center text-center space-y-3 px-8">
              <div className="w-12 h-12 rounded-2xl bg-cyan-500/8 border border-cyan-500/15 flex items-center justify-center">
                <Code2 className="w-6 h-6 text-cyan-500/50" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-400">Select a module</p>
                <p className="text-xs text-slate-600 mt-1">Pick a DSPy prompt module from the list to view, edit, and test it.</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  AGENTS TAB — per-agent LLM assignments
// ═══════════════════════════════════════════════════════════════

// Canonical list of agent nodes with human labels and their default role
const AGENT_NODES: Array<{ id: string; label: string; description: string; defaultRole: string }> = [
  { id: "narrator",         label: "Narrator",         description: "Generates prose narrative from turn context",           defaultRole: "heavy" },
  { id: "canonkeeper",      label: "CanonKeeper",      description: "Evaluates proposals and commits to Neo4j",              defaultRole: "heavy" },
  { id: "context_assembly", label: "Context Assembly", description: "Formulates queries and ranks retrieved context",        defaultRole: "standard" },
  { id: "resolver",         label: "Resolver",         description: "Dice resolution and action routing",                    defaultRole: "light" },
  { id: "analyzer",         label: "Analyzer",         description: "Extracts axioms, entities and lore from documents",     defaultRole: "standard" },
  { id: "indexer",          label: "Indexer",           description: "Chunks documents and generates embeddings",            defaultRole: "light" },
  { id: "npc_voice",        label: "NPC Voice",        description: "Generates in-character NPC dialogue",                  defaultRole: "standard" },
  { id: "scene_loop",       label: "Scene Loop",       description: "Orchestrates a scene turn (context→resolve→narrate)",  defaultRole: "standard" },
  { id: "story_loop",       label: "Story Loop",       description: "Manages campaign arc progression",                     defaultRole: "standard" },
  { id: "turn_loop",        label: "Turn Loop",        description: "Parses intent and runs a single player turn",          defaultRole: "standard" },
  { id: "ingestion",        label: "Ingestion",        description: "End-to-end document ingestion pipeline",               defaultRole: "light" },
];

const ROLE_BADGE: Record<string, string> = {
  heavy:    "text-purple-300 bg-purple-500/10 border-purple-500/20",
  standard: "text-cyan-300   bg-cyan-500/10   border-cyan-500/20",
  light:    "text-emerald-300 bg-emerald-500/10 border-emerald-500/20",
};

function AgentRow({
  agent,
  assignment,
  providers,
  onSave,
  onClear,
}: {
  agent: typeof AGENT_NODES[0];
  assignment: NodeAssignment | undefined;
  providers: LLMConnection[];
  onSave: (nodeId: string, providerId: string, overrides: Record<string, number | null>) => void;
  onClear: (nodeId: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState(assignment?.provider_id ?? "");
  const [temperature, setTemperature] = useState<string>(
    assignment?.param_overrides?.temperature != null ? String(assignment.param_overrides.temperature) : "",
  );
  const [maxTokens, setMaxTokens] = useState<string>(
    assignment?.param_overrides?.max_tokens != null ? String(assignment.param_overrides.max_tokens) : "",
  );

  const save = () => {
    if (!selectedProvider) return;
    const overrides: Record<string, number | null> = {};
    if (temperature !== "") overrides.temperature = parseFloat(temperature);
    if (maxTokens !== "")   overrides.max_tokens  = parseInt(maxTokens, 10);
    onSave(agent.id, selectedProvider, overrides);
    setEditing(false);
  };

  const hasAssignment = Boolean(assignment?.provider_id);
  const providerMeta = assignment ? PROVIDER_META[assignment.provider ?? ""] : null;
  const connectedProvider = providers.find((p) => p.id === assignment?.provider_id);

  return (
    <div className="glass-dark rounded-xl border border-white/5 p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-white/4 border border-white/8 flex items-center justify-center flex-shrink-0">
            <Zap className="w-4 h-4 text-slate-400" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-slate-200">{agent.label}</span>
              <span className={cn("text-[9px] px-1.5 py-0.5 rounded-full border font-medium uppercase tracking-wide", ROLE_BADGE[agent.defaultRole])}>
                {agent.defaultRole}
              </span>
            </div>
            <p className="text-xs text-slate-600 truncate">{agent.description}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {hasAssignment && !editing && (
            <button
              onClick={() => { setEditing(true); setSelectedProvider(assignment!.provider_id); }}
              className="btn-ghost py-1 px-2 text-xs"
            >
              <ChevronDown className="w-3 h-3" /> Edit
            </button>
          )}
          {hasAssignment && (
            <button onClick={() => onClear(agent.id)} className="p-1.5 rounded text-slate-600 hover:text-red-400 transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          {!hasAssignment && !editing && (
            <button
              onClick={() => setEditing(true)}
              className="btn-ghost py-1 px-2 text-xs text-cyan-400 hover:text-cyan-300 border border-cyan-500/20"
            >
              <Plus className="w-3 h-3" /> Assign
            </button>
          )}
        </div>
      </div>

      {/* Current assignment badge */}
      {hasAssignment && !editing && connectedProvider && (
        <div className={cn(
          "flex items-center gap-2 px-3 py-2 rounded-lg border text-xs",
          connectedProvider.status === "connected"
            ? (providerMeta ? `${providerMeta.bg} ${providerMeta.border} ${providerMeta.color}` : "bg-white/4 border-white/10 text-slate-300")
            : "bg-white/4 border-white/8 text-slate-500",
        )}>
          <Cpu className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="font-medium">{connectedProvider.name}</span>
          <span className="text-slate-600">·</span>
          <code className="font-mono text-[11px]">{connectedProvider.model}</code>
          {assignment?.param_overrides?.temperature != null && (
            <span className="ml-auto text-[10px] text-slate-500">temp {assignment.param_overrides.temperature}</span>
          )}
          {assignment?.param_overrides?.max_tokens != null && (
            <span className="text-[10px] text-slate-500">max_tok {assignment.param_overrides.max_tokens}</span>
          )}
        </div>
      )}

      {!hasAssignment && !editing && (
        <p className="text-[11px] text-slate-700 italic">Uses the default provider</p>
      )}

      {/* Inline editor */}
      {editing && (
        <div className="space-y-3 pt-1 border-t border-white/5">
          <div className="space-y-1">
            <label className="text-[10px] text-slate-600 uppercase tracking-wide">Provider</label>
            <select
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value)}
              className="input-cyber w-full"
            >
              <option value="">Select provider…</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.model} {p.is_default ? "(default)" : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] text-slate-600 uppercase tracking-wide">Temperature override</label>
              <input
                type="number"
                min="0" max="2" step="0.05"
                value={temperature}
                onChange={(e) => setTemperature(e.target.value)}
                placeholder="e.g. 0.7 (blank = provider default)"
                className="input-cyber w-full"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] text-slate-600 uppercase tracking-wide">Max tokens override</label>
              <input
                type="number"
                min="1" step="256"
                value={maxTokens}
                onChange={(e) => setMaxTokens(e.target.value)}
                placeholder="e.g. 4096 (blank = provider default)"
                className="input-cyber w-full"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setEditing(false)} className="btn-ghost flex-1 justify-center text-xs">Cancel</button>
            <button
              onClick={save}
              disabled={!selectedProvider}
              className="btn-cyber flex-1 justify-center text-xs"
            >
              <Check className="w-3.5 h-3.5" /> Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

type AgentsSubTab = "assignments" | "prompts";

function AgentsTab() {
  const qc = useQueryClient();
  const [subTab, setSubTab] = useState<AgentsSubTab>("assignments");

  const { data: providers = [], isLoading: loadingProviders } = useLLMProviders();
  const { data: assignments = [], isLoading: loadingAssignments } = useLLMAssignments();

  const save = useMutation({
    mutationFn: ({ nodeId, providerId, overrides }: { nodeId: string; providerId: string; overrides: Record<string, number | null> }) =>
      llmApi.setAssignment(nodeId, { provider_id: providerId, param_overrides: overrides }),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.assignments }),
  });

  const clear = useMutation({
    mutationFn: (nodeId: string) => llmApi.deleteAssignment(nodeId),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.assignments }),
  });

  const assignmentByNode = Object.fromEntries(assignments.map((a) => [a.node_name, a]));
  const isLoading = loadingProviders || loadingAssignments;

  return (
    <div className="space-y-6">
      {/* Sub-tab switcher */}
      <div className="flex items-center gap-1 border-b border-white/5 pb-1">
        <button
          onClick={() => setSubTab("assignments")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
            subTab === "assignments"
              ? "bg-network-500/10 text-network-300 bg-cyan-500/10 text-cyan-300 border border-cyan-500/25"
              : "text-slate-500 hover:text-slate-300 border border-transparent",
          )}
        >
          <Network className="w-3.5 h-3.5" />
          LLM Assignments
        </button>
        <button
          onClick={() => setSubTab("prompts")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
            subTab === "prompts"
              ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/25"
              : "text-slate-500 hover:text-slate-300 border border-transparent",
          )}
        >
          <Zap className="w-3.5 h-3.5" />
          Prompt Modules
        </button>
      </div>

      {subTab === "assignments" && (
        <>
          <div>
            <h2 className="text-lg font-bold text-slate-100">Agent LLM Assignments</h2>
            <p className="text-sm text-slate-500 mt-1">
              Configure which LLM provider each agent uses. Unassigned agents fall back to the default provider.
              You can override temperature and max tokens per-agent.
            </p>
          </div>

          {isLoading ? (
            <div className="flex items-center gap-2 text-slate-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </div>
          ) : providers.length === 0 ? (
            <div className="glass-dark rounded-xl border border-amber-500/20 bg-amber-500/5 p-5 flex items-start gap-3">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-amber-300">
                No LLM providers configured. Add a provider in the <span className="font-semibold">LLM Providers</span> tab first.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              {AGENT_NODES.map((agent) => (
                <AgentRow
                  key={agent.id}
                  agent={agent}
                  assignment={assignmentByNode[agent.id]}
                  providers={providers}
                  onSave={(nodeId, providerId, overrides) => save.mutate({ nodeId, providerId, overrides })}
                  onClear={(nodeId) => clear.mutate(nodeId)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {subTab === "prompts" && <PromptsPanel />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  MAIN PAGE
// ═══════════════════════════════════════════════════════════════

export default function SettingsPage() {
  const [tab, setTab] = useState<SettingsTab>("llm");

  return (
    <div className="flex flex-col h-full">
      {/* Header + Tabs */}
      <div className="flex items-center gap-4 px-6 py-3 border-b border-white/5 glass-dark flex-shrink-0">
        <Settings className="w-5 h-5 text-purple-400 flex-shrink-0" />
        <h1 className="text-sm font-bold text-slate-200">Settings</h1>
        <div className="h-5 w-px bg-white/10" />
        <div className="flex items-center gap-1">
          {SETTINGS_TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                tab === id
                  ? "bg-purple-500/10 text-purple-300 border border-purple-500/25"
                  : "text-slate-500 hover:text-slate-300 border border-transparent",
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto px-8 py-8">
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15 }}
          >
            {tab === "llm" && <LLMTab />}
            {tab === "agents" && <AgentsTab />}
            {tab === "testbed" && <BenchmarkTestbedTab />}
            {tab === "databases" && <DatabasesTab />}
            {tab === "tone" && <ToneTabLink />}
            {tab === "performance" && <PerformanceTab />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
//  TONE TAB (F1-5a — moved to Forge → Style, this is just a link)
// ═══════════════════════════════════════════════════════════════

function ToneTabLink() {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-3 text-slate-500">
      <Palette className="w-10 h-10 opacity-30" />
      <h2 className="text-sm font-bold text-slate-300">Tone management moved to the Forge</h2>
      <p className="text-xs max-w-sm text-center">
        Tone profiles, libraries and tags now live in the Forge Style section.
      </p>
      <Link
        href="/forge/style"
        className="mt-2 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-sm text-white"
      >
        Open Forge → Style
      </Link>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  PERFORMANCE TAB (T-038 — performance monitoring bridge)
// ═══════════════════════════════════════════════════════════════

function PerformanceTab() {
  const overviewQ = useQuery({
    queryKey: ["performance", "overview"],
    queryFn: () => performanceApi.overview(),
    refetchInterval: 15_000,
  });
  const slowQ = useQuery({
    queryKey: ["performance", "slow"],
    queryFn: () => performanceApi.slowQueries(15),
    refetchInterval: 30_000,
  });
  const alertsQ = useQuery({
    queryKey: ["performance", "alerts"],
    queryFn: () => performanceApi.alerts({ limit: 15 }),
    refetchInterval: 30_000,
  });

  const o = overviewQ.data;

  return (
    <div className="space-y-8 max-w-5xl">
      <div>
        <h2 className="text-lg font-bold text-slate-100">Performance</h2>
        <p className="text-sm text-slate-500 mt-1">
          Query latency, slow operations and alert history.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Requests", value: o?.request_count ?? "—" },
          { label: "Avg latency", value: o ? `${o.avg_latency_ms.toFixed(0)} ms` : "—" },
          { label: "p95", value: o ? `${o.p95_ms.toFixed(0)} ms` : "—" },
          { label: "Slow queries", value: o?.slow_query_count ?? "—" },
        ].map((c) => (
          <div key={c.label} className="bg-zinc-900/60 border border-zinc-800 rounded-lg px-4 py-3">
            <div className="text-[10px] uppercase tracking-wide text-slate-500">{c.label}</div>
            <div className="text-xl font-bold text-slate-100 mt-1">{c.value}</div>
          </div>
        ))}
      </div>

      <div>
        <h3 className="text-sm font-bold text-slate-200 mb-2">Slow queries</h3>
        {(slowQ.data ?? []).length === 0 ? (
          <p className="text-xs text-slate-500">None recorded.</p>
        ) : (
          <div className="space-y-1">
            {(slowQ.data ?? []).map((q) => (
              <div
                key={q.query_id}
                className="flex items-center justify-between gap-4 bg-zinc-900/40 border border-zinc-800 rounded-lg px-4 py-2"
              >
                <span className="text-xs text-slate-400 truncate">{q.query_summary}</span>
                <span className="text-xs font-mono text-amber-400 flex-shrink-0">
                  {q.duration_ms.toFixed(0)} ms
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-bold text-slate-200 mb-2">Alerts</h3>
        {(alertsQ.data ?? []).length === 0 ? (
          <p className="text-xs text-slate-500">No alerts.</p>
        ) : (
          <div className="space-y-1">
            {(alertsQ.data ?? []).map((a) => (
              <div
                key={a.alert_id}
                className="flex items-center justify-between gap-4 bg-zinc-900/40 border border-zinc-800 rounded-lg px-4 py-2"
              >
                <span className="text-xs text-slate-400 truncate">{a.message}</span>
                <span
                  className={
                    a.severity === "critical"
                      ? "text-xs text-red-400"
                      : a.severity === "warning"
                        ? "text-xs text-amber-400"
                        : "text-xs text-slate-500"
                  }
                >
                  {a.severity}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
