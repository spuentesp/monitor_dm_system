"use client";

import { useEffect } from "react";
import { PageError } from "@/components/PageError";
import { errorMessage } from "@/lib/errors";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[prompts error]", error);
  }, [error]);
  return <PageError title="Prompt Curation hit a snag" detail={errorMessage(error)} />;
}
