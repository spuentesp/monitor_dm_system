import { describe, it, expect } from "vitest";
import { chunkLorebookEntries, lorebookChunksForText } from "./lorebookChunking";

describe("lorebookChunksForText", () => {
  it("returns empty array for empty text", () => {
    expect(lorebookChunksForText("", 1000)).toEqual([]);
  });

  it("returns empty array for whitespace-only text", () => {
    expect(lorebookChunksForText("   \n\t  ", 1000)).toEqual([]);
  });

  it("chunks text by size", () => {
    const text = "a".repeat(2500);
    const chunks = lorebookChunksForText(text, 1000);
    expect(chunks.length).toBe(3);
    expect(chunks[0].length).toBe(1000);
    expect(chunks[1].length).toBe(1000);
    expect(chunks[2].length).toBe(500);
  });

  it("clamps chunk_size to a minimum of 200 chars", () => {
    const text = "a".repeat(1000);
    const chunks = lorebookChunksForText(text, 50); // below minimum
    // Should clamp to 200, so 1000 / 200 = 5 chunks
    expect(chunks.length).toBe(5);
  });
});

describe("chunkLorebookEntries", () => {
  it("splits entries into batches of the requested size", () => {
    const entries = Array.from({ length: 50 }, (_, i) => ({ id: i, content: `c${i}` }));
    const batches = chunkLorebookEntries(entries, 20);
    expect(batches.length).toBe(3);
    expect(batches[0].length).toBe(20);
    expect(batches[1].length).toBe(20);
    expect(batches[2].length).toBe(10);
  });

  it("returns a single batch when entries fit", () => {
    const entries = Array.from({ length: 5 }, (_, i) => ({ id: i }));
    const batches = chunkLorebookEntries(entries, 20);
    expect(batches.length).toBe(1);
    expect(batches[0].length).toBe(5);
  });

  it("handles empty input", () => {
    expect(chunkLorebookEntries([], 20)).toEqual([]);
  });
});
