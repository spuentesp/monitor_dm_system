// Pure helpers for lorebook document ingestion (M3-G.2). Kept out of the
// component so the chunking and batching are unit-testable in isolation.

const MIN_CHUNK_SIZE = 200;

/**
 * Split `text` into chunks of at most `size` characters (clamped to a
 * minimum of MIN_CHUNK_SIZE). Empty / whitespace-only inputs return [].
 */
export function lorebookChunksForText(text: string, size: number): string[] {
  if (!text || !text.trim()) return [];
  const clampedSize = Math.max(MIN_CHUNK_SIZE, size);
  const chunks: string[] = [];
  for (let i = 0; i < text.length; i += clampedSize) {
    const chunk = text.slice(i, i + clampedSize).trim();
    if (chunk) chunks.push(chunk);
  }
  return chunks;
}

/**
 * Split an array of entries into batches of `batchSize`. The last batch
 * may be smaller. Returns an empty array for empty input.
 *
 * Lorebook ingestion batches POSTs in groups of ~20 so a 300-chunk
 * document doesn't blow the backend's default 30s request timeout on a
 * single bulkCreate call.
 */
export function chunkLorebookEntries<T>(entries: readonly T[], batchSize: number): T[][] {
  if (entries.length === 0) return [];
  const batches: T[][] = [];
  for (let i = 0; i < entries.length; i += batchSize) {
    batches.push(entries.slice(i, i + batchSize));
  }
  return batches;
}
