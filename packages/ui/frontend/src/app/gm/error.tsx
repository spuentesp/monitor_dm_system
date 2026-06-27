"use client";

import { useEffect } from "react";
import { PageError } from "@/components/PageError";
import { errorMessage } from "@/lib/errors";

export default function GMError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => { console.error("[GM route error]", error); }, [error]);
  return <PageError title="GM Assistant hit a snag" detail={errorMessage(error)} />;
}
