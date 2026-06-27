"use client";

import { useEffect } from "react";
import { PageError } from "@/components/PageError";
import { errorMessage } from "@/lib/errors";

export default function WorldsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to console so devs can find the trace; in prod we'd send to a
    // real observability backend here.
    console.error("[Worlds route error]", error);
  }, [error]);

  return (
    <PageError
      title="Worlds hit a snag"
      detail={errorMessage(error)}
    />
  );
}
