"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Cpu,
  Gauge,
  ShieldOff,
  Ticket,
  UserCog,
} from "lucide-react";
import { authApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PageSkeleton } from "@/components/PageSkeleton";
import { AdminUsersTab } from "@/components/admin/AdminUsersTab";
import { AdminInvitesTab } from "@/components/admin/AdminInvitesTab";
import { AdminUsageTab } from "@/components/admin/AdminUsageTab";
import { LLMProvidersPanel } from "@/components/settings/LLMProvidersPanel";

const ADMIN_TABS = [
  { id: "users", label: "Users", icon: UserCog },
  { id: "invites", label: "Invites", icon: Ticket },
  { id: "usage", label: "Usage", icon: Gauge },
  { id: "providers", label: "Providers", icon: Cpu },
] as const;

type AdminTab = (typeof ADMIN_TABS)[number]["id"];

export default function AdminPage() {
  const [tab, setTab] = useState<AdminTab>("users");

  const { data: me, isLoading: meLoading } = useQuery({
    queryKey: ["auth-me"],
    queryFn: authApi.me,
    retry: false,
    staleTime: 60_000,
  });

  if (meLoading || !me) {
    // AuthGate owns the 401 → /login redirect; keep a skeleton meanwhile.
    return <PageSkeleton rows={5} />;
  }
  if (!me.user.is_admin) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="glass rounded-2xl border border-red-500/20 p-8 text-center space-y-2">
          <ShieldOff className="mx-auto h-8 w-8 text-red-400" />
          <p className="text-sm text-slate-300">Operator access required.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-4 px-6 py-3 border-b border-white/5 glass-dark flex-shrink-0">
        <ShieldOff className="w-5 h-5 text-amber-400 flex-shrink-0" />
        <h1 className="text-sm font-bold text-slate-200">Administration</h1>
        <div className="h-5 w-px bg-white/10" />
        <div className="flex items-center gap-1">
          {ADMIN_TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                tab === id
                  ? "bg-amber-500/10 text-amber-300 border border-amber-500/25"
                  : "text-slate-500 hover:text-slate-300 border border-transparent",
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-8">
        <div className="mx-auto max-w-6xl">
          {tab === "users" && <AdminUsersTab meId={me.user.id} />}
          {tab === "invites" && <AdminInvitesTab />}
          {tab === "usage" && <AdminUsageTab />}
          {tab === "providers" && <LLMProvidersPanel />}
        </div>
      </div>
    </div>
  );
}
