import Link from "next/link";
import { Compass } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md w-full glass rounded-2xl border border-amber-500/20 p-8 space-y-4 text-center">
        <div className="flex justify-center">
          <div className="w-14 h-14 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center">
            <Compass className="w-7 h-7 text-amber-400" />
          </div>
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-100">Lost the trail</h2>
          <p className="mt-1 text-sm text-slate-400 leading-relaxed">
            That page is not on any of our maps. Try the worlds tree, or head back to the gate.
          </p>
        </div>
        <div className="flex items-center justify-center gap-2 pt-2">
          <Link href="/" className="btn-cyber text-xs">Gate</Link>
          <Link href="/worlds" className="btn-ghost text-xs">Worlds</Link>
        </div>
      </div>
    </div>
  );
}
