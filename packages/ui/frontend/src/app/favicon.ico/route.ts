// Next.js 15 doesn't auto-route /favicon.ico → app/icon.tsx (which serves /icon).
// Without this, browsers that hard-request /favicon.ico 404. We redirect to /icon
// so the generated PNG handles the request and dev tools that probe /favicon.ico
// directly (Chrome DevTools, Lighthouse) stop 404'ing.
import { redirect } from "next/navigation";

export const dynamic = "force-static";

export function GET() {
  redirect("/icon");
}