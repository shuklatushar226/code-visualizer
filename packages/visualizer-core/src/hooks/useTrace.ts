/**
 * useTrace — fetches a Trace Event Protocol document from the backend.
 */

import { useEffect, useState } from "react";
import type { Trace } from "@dsa-viz/trace-schema";
import { traceClient } from "../lib/traceClient";

export interface UseTraceResult {
  trace: Trace | null;
  loading: boolean;
  error: string | null;
  retrace: (source: string, language: "python" | "cpp", stdin?: string) => void;
}

export function useTrace(baseUrl = "http://localhost:8000"): UseTraceResult {
  const [trace, setTrace] = useState<Trace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const retrace = (
    source: string,
    language: "python" | "cpp",
    stdin = ""
  ) => {
    setLoading(true);
    setError(null);
    traceClient(baseUrl)
      .trace({ source, language, stdin })
      .then((t) => setTrace(t))
      .catch((e) => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  };

  return { trace, loading, error, retrace };
}
