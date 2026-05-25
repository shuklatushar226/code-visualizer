import type { Trace } from "@dsa-viz/trace-schema";

export interface TraceRequest {
  source: string;
  language: "python" | "cpp";
  stdin?: string;
}

export function traceClient(baseUrl: string) {
  return {
    async trace(req: TraceRequest): Promise<Trace> {
      const r = await fetch(`${baseUrl}/trace`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!r.ok) {
        const msg = await r.text();
        throw new Error(`backend returned ${r.status}: ${msg}`);
      }
      return (await r.json()) as Trace;
    },
    async health() {
      const r = await fetch(`${baseUrl}/healthz`);
      return r.ok;
    },
  };
}
