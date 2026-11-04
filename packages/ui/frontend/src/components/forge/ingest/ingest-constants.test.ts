import { describe, expect, it } from "vitest";
import { canResumeJob, decompositionSummary, isDecompositionJob } from "./ingest-constants";

describe("book decomposition jobs", () => {
  it("resumes paused or failed decomposition jobs only", () => {
    expect(canResumeJob({ current_stage: "decompose", status: "paused" })).toBe(true);
    expect(canResumeJob({ current_stage: "decompose", status: "failed" })).toBe(true);
    expect(canResumeJob({ current_stage: "decompose", status: "running" })).toBe(false);
    expect(canResumeJob({ current_stage: "decompose", status: "completed" })).toBe(false);
    expect(canResumeJob({ current_stage: "analyze", status: "failed" })).toBe(false);
    expect(canResumeJob({ current_stage: null, status: "paused" })).toBe(false);
  });

  it("tells decomposition jobs from normal ingests", () => {
    expect(isDecompositionJob({ current_stage: "decompose" })).toBe(true);
    expect(isDecompositionJob({ current_stage: "embed" })).toBe(false);
  });

  it("summarizes progress and only mentions what applies", () => {
    expect(decompositionSummary({ decomposition: null })).toBeNull();
    expect(decompositionSummary({})).toBeNull();
    const base = {
      sentences_total: 10,
      sentences_done: 4,
      sentences_quarantined: 0,
      claims_kept: 0,
      claims_held_back: 0,
      pause_reason: null,
    };
    expect(decompositionSummary({ decomposition: base })).toBe("4/10 sentences");
    expect(
      decompositionSummary({
        decomposition: { ...base, sentences_done: 10, claims_kept: 8, sentences_quarantined: 1, claims_held_back: 2 },
      }),
    ).toBe("10/10 sentences · 8 claims kept · 1 need a person · 2 held back");
  });
});
