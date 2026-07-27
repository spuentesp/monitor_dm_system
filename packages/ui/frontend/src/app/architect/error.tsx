"use client";

import { useEffect } from "react";
import { PageError } from "@/components/PageError";
import { errorMessage } from "@/lib/errors";

export default function ArchitectError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => { console.error("[World Architect route error]", error); }, [error]);
  return <PageError title="World Architect hit a snag" detail={errorMessage(error)} />;
}
