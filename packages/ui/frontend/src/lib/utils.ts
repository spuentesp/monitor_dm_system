import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "N/A";
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + "…" : text;
}

export function statusColor(
  status: "online" | "offline" | "degraded" | "connected" | "error" | "unconfigured" | string,
): string {
  switch (status) {
    case "online":
    case "connected":
      return "text-emerald-400";
    case "offline":
    case "error":
      return "text-red-400";
    case "degraded":
      return "text-amber-400";
    default:
      return "text-slate-500";
  }
}

export function statusDotClass(status: string): string {
  switch (status) {
    case "online":
    case "connected":
      return "status-online";
    case "offline":
    case "error":
      return "status-offline";
    case "degraded":
      return "status-degraded";
    default:
      return "bg-slate-600";
  }
}
