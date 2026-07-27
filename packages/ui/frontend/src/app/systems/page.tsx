import { redirect } from "next/navigation";

// F1-1: Systems moved under the Forge route group. Keep old deep links
// (e.g. /systems?id=<game_system_id>) working by forwarding the query string.
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    if (typeof value === "string") params.set(key, value);
  }
  const qs = params.toString();
  redirect(qs ? `/forge/systems?${qs}` : "/forge/systems");
}
