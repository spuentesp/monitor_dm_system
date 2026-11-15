// CF-10 (G02) — audio capture: upload a recording, review its transcript,
// queue a segment into the CF-1 capture flow.
//
// The upload is a multipart form, so it cannot use the shared `req` helper
// (that one sets a JSON content type).

import { ApiError, apiUrl, req } from "@/lib/api";

export interface TranscriptSegment {
  id: string;
  index: number;
  start: number;
  end: number;
  text: string;
  speaker: string | null;
  reviewed: boolean;
}

export interface AudioTranscript {
  transcript_id: string;
  universe_id: string;
  provider: string;
  model: string;
  text: string;
  language: string | null;
  duration: number | null;
  segments: TranscriptSegment[];
  audio_key: string | null;
}

async function post<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(apiUrl(path), { method: "POST", body });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json() as Promise<T>;
}

export const gmAudioApi = {
  /** Upload a recording and transcribe it. */
  transcribe: (
    universeId: string,
    file: File,
    options?: { session_id?: string | null; scene_id?: string | null; story_id?: string | null },
  ) => {
    const form = new FormData();
    form.append("universe_id", universeId);
    form.append("file", file);
    if (options?.session_id) form.append("session_id", options.session_id);
    if (options?.scene_id) form.append("scene_id", options.scene_id);
    if (options?.story_id) form.append("story_id", options.story_id);
    return post<AudioTranscript>("/gm/audio/transcribe", form);
  },

  /** Read a stored transcript. */
  getTranscript: (transcriptId: string) =>
    fetch(apiUrl(`/gm/audio/transcripts/${transcriptId}`)).then(async (res) => {
      if (!res.ok) throw new ApiError(res.status, await res.text());
      return res.json() as Promise<AudioTranscript>;
    }),

  /** Queue one reviewed segment into the capture flow. */
  queueSegment: (transcriptId: string, segmentIndex: number, text?: string, speaker?: string) =>
    req<{ transcript_id: string; segment_index: number; proposal_ids: string[] }>(
      `/gm/audio/transcripts/${transcriptId}/queue`,
      {
        method: "POST",
        body: JSON.stringify({ segment_index: segmentIndex, text: text ?? null, speaker: speaker ?? null }),
      },
    ),
};
