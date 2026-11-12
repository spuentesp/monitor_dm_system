"use client";

import { useRef, useState } from "react";
import { AudioLines, Loader2, Mic, Send } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { gmAudioApi, type AudioTranscript, type TranscriptSegment } from "@/lib/gm-audio-api";
import { cn } from "@/lib/utils";

/**
 * Audio capture (CF-10 / G02).
 *
 * A GM running a game cannot type notes. This panel takes the recording
 * instead: upload it, read the transcript, fix what the transcriber got
 * wrong, and queue a segment into the CF-1 capture flow — the same flow a
 * typed entry goes through, so the proposals are the same proposals.
 *
 * Nothing becomes canon here. A queued segment becomes a *pending*
 * proposal waiting in the CF-8 queue.
 */

interface AudioTranscriptPanelProps {
  universeId: string | null;
  sessionId?: string | null;
  sceneId?: string | null;
  storyId?: string | null;
}

export function AudioTranscriptPanel({
  universeId,
  sessionId,
  sceneId,
  storyId,
}: AudioTranscriptPanelProps) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [transcript, setTranscript] = useState<AudioTranscript | null>(null);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [queued, setQueued] = useState<Record<number, number>>({});

  const transcribe = useMutation({
    mutationFn: (file: File) =>
      gmAudioApi.transcribe(universeId!, file, {
        session_id: sessionId ?? null,
        scene_id: sceneId ?? null,
        story_id: storyId ?? null,
      }),
    onSuccess: (data) => {
      setTranscript(data);
      setEdits({});
      setQueued({});
    },
  });

  const queue = useMutation({
    mutationFn: (segment: TranscriptSegment) =>
      gmAudioApi.queueSegment(
        transcript!.transcript_id,
        segment.index,
        edits[segment.index] ?? segment.text,
      ),
    onSuccess: (_data, segment) =>
      setQueued((prev) => ({
        ...prev,
        [segment.index]: (prev[segment.index] ?? 0) + 1,
      })),
  });

  if (!universeId) {
    return (
      <p className="text-[10px] text-slate-600">Select a universe to record a session.</p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <input
          ref={fileRef}
          type="file"
          accept="audio/*"
          aria-label="Recording"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) transcribe.mutate(file);
          }}
        />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={transcribe.isPending}
          className="btn-cyber text-xs py-1 px-3 flex items-center gap-1.5"
        >
          {transcribe.isPending ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Mic className="w-3 h-3" />
          )}
          {transcribe.isPending ? "Transcribing…" : "Upload a recording"}
        </button>
        {transcript?.provider && (
          <span className="text-[9px] text-slate-600">
            transcribed by {transcript.provider}
            {transcript.model ? ` (${transcript.model})` : ""}
          </span>
        )}
      </div>

      {transcribe.isError && (
        <p className="text-[10px] text-red-400">The recording could not be transcribed.</p>
      )}

      {transcript && transcript.segments.length === 0 && (
        <p className="text-[10px] text-slate-600">The recording has no speech in it.</p>
      )}

      {transcript && transcript.segments.length > 0 && (
        <div className="space-y-2">
          {transcript.segments.map((segment) => {
            const value = edits[segment.index] ?? segment.text;
            const queuedCount = queued[segment.index] ?? 0;
            return (
              <div key={segment.id} className="glass-dark rounded-lg border border-white/5 p-2.5 space-y-1.5">
                <div className="flex items-center gap-2 text-[9px] text-slate-600">
                  <AudioLines className="w-3 h-3" />
                  <span>
                    {segment.start.toFixed(1)}s – {segment.end.toFixed(1)}s
                  </span>
                  {segment.speaker && <span>· {segment.speaker}</span>}
                </div>
                <textarea
                  value={value}
                  aria-label={`Segment ${segment.index + 1}`}
                  onChange={(e) =>
                    setEdits((prev) => ({ ...prev, [segment.index]: e.target.value }))
                  }
                  className="input-cyber w-full text-[11px] min-h-[48px]"
                />
                <div className="flex items-center justify-end gap-2">
                  {queuedCount > 0 && (
                    <span className="text-[9px] text-emerald-400">
                      queued as {queuedCount} proposal{queuedCount > 1 ? "s" : ""}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => queue.mutate(segment)}
                    disabled={queue.isPending || !value.trim()}
                    className="btn-cyber text-[10px] py-1 px-2 flex items-center gap-1"
                    aria-label={`Queue segment ${segment.index + 1}`}
                  >
                    {queue.isPending ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Send className="w-3 h-3" />
                    )}
                    Queue as entry
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {queue.isError && (
        <p className={cn("text-[10px] text-red-400")}>
          The segment could not be queued — it needs a scene or a story to belong to.
        </p>
      )}
    </div>
  );
}

export default AudioTranscriptPanel;
