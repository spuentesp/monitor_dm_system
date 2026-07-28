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
    console.error("[worlds error]", error);
  }, [error]);
  return <PageError title="Worlds hit a snag" detail={errorMessage(error)} />;
}
