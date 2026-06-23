import { Suspense } from "react";
import PlayConsole from "@/components/play/PlayConsole";

export default function PlayPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading play console…</div>}>
      <PlayConsole />
    </Suspense>
  );
}
