import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Trace } from "../src/index";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCHEMA = JSON.parse(
  readFileSync(path.join(HERE, "..", "schema", "trace.schema.json"), "utf-8"),
);

const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const validate = ajv.compile(SCHEMA);

/** A minimal-but-complete trace exercising every required schema field. */
const validTrace: Trace = {
  version: "0.1",
  language: "python",
  source: "x = 1\ny = 2\n",
  stdin: "",
  stdout: "",
  stderr: "",
  exit: { status: "ok", message: null, truncated: false },
  events: [
    {
      t: 0,
      kind: "step",
      line: 1,
      file: "main.py",
      stack: [
        {
          func: "<module>",
          file: "main.py",
          line: 1,
          locals: { x: { kind: "int", v: 1 } },
          args: [],
        },
      ],
      heap: {},
      stdout_delta: null,
      exception: null,
    },
  ],
};

describe("trace.schema.json", () => {
  it("validates a minimal-but-complete Python trace", () => {
    const ok = validate(validTrace);
    if (!ok) console.error(validate.errors);
    expect(ok).toBe(true);
  });

  it("validates a cpp trace with the same shape", () => {
    const cpp = { ...validTrace, language: "cpp" as const };
    expect(validate(cpp)).toBe(true);
  });

  it("validates a trace with a list on the heap and a ref local", () => {
    const trace: Trace = {
      ...validTrace,
      events: [
        {
          ...validTrace.events[0],
          stack: [
            {
              func: "<module>",
              file: "main.py",
              line: 1,
              locals: { xs: { kind: "ref", id: "h_0" } },
              args: [],
            },
          ],
          heap: {
            h_0: { kind: "list", items: [{ kind: "int", v: 1 }, { kind: "int", v: 2 }] },
          },
        },
      ],
    };
    expect(validate(trace)).toBe(true);
  });

  it("rejects a trace missing version", () => {
    const bad = { ...validTrace } as unknown as Record<string, unknown>;
    delete bad.version;
    expect(validate(bad)).toBe(false);
  });

  it("rejects a trace with an unknown language", () => {
    const bad = { ...validTrace, language: "rust" };
    expect(validate(bad)).toBe(false);
  });

  it("rejects an event without the required keys", () => {
    const bad = {
      ...validTrace,
      events: [{ t: 0, kind: "step" }], // missing line, stack, heap
    };
    expect(validate(bad)).toBe(false);
  });

  it("rejects a Value with an unknown kind", () => {
    const bad: any = {
      ...validTrace,
      events: [
        {
          ...validTrace.events[0],
          stack: [
            {
              func: "<module>",
              file: "main.py",
              line: 1,
              locals: { x: { kind: "imaginary", v: 7 } },
              args: [],
            },
          ],
        },
      ],
    };
    expect(validate(bad)).toBe(false);
  });
});
