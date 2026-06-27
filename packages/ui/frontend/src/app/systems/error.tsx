"use client";

import { useEffect } from "react";
import { PageError } from "@/components/PageError";
import { errorMessage } from "@/lib/errors";

export default function SystemsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to console so devs can find the trace; in prod we'd send to a
    // real observability backend here.
    console.error("[Systems route error]", error);
  }, [error]);

  return (
    <PageError
      title="Systems hit a snag"
      detail={errorMessage(error)}
    />
  );
}
