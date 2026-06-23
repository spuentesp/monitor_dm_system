"use client";

import { HistoryTab } from "@/components/HistoryTab";

export default function HistoryPage() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-8 py-10 space-y-6">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-slate-100">History</h1>
          <p className="text-sm text-slate-500">
            Q-10 audit trail — every canonical change CanonKeeper has committed, newest first.
          </p>
        </div>
        <HistoryTab />
      </div>
    </div>
  );
}
