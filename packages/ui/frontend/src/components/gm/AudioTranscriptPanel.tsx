"use client";

import { useEffect, useRef, useState } from "react";
import { AudioLines, Loader2, Mic, Send } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
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
  const playerRef = useRef<HTMLAudioElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const [recording, setRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const [transcript, setTranscript] = useState<AudioTranscript | null>(null);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [speakers, setSpeakers] = useState<Record<number, string>>({});
  const [queued, setQueued] = useState<Record<number, number>>({});

  useEffect(() => () => { if (audioUrl) URL.revokeObjectURL(audioUrl); }, [audioUrl]);
  useEffect(() => () => {
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
  }, []);

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
      setSpeakers({});
      setQueued({});
    },
  });

  const queue = useMutation({
    mutationFn: (segment: TranscriptSegment) =>
      gmAudioApi.queueSegment(
        transcript!.transcript_id,
        segment.index,
        edits[segment.index] ?? segment.text,
        speakers[segment.index] ?? segment.speaker ?? "",
      ),
    onSuccess: (data, segment) => {
      setQueued((prev) => ({
        ...prev,
        [segment.index]: data.proposal_ids.length,
      }));
      void queryClient.invalidateQueries({ queryKey: ["chat", sessionId, "messages"] });
    },
  });

  const startRecording = async () => {
    try {
      setRecordingError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        setRecording(false);
        const file = new File(chunks, "recording.webm", { type: recorder.mimeType || "audio/webm" });
        setAudioUrl(URL.createObjectURL(file));
        transcribe.mutate(file);
      };
      recorder.start();
      setRecording(true);
    } catch {
      setRecordingError("Could not start the microphone.");
    }
  };

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
            if (file) {
              setAudioUrl(URL.createObjectURL(file));
              transcribe.mutate(file);
            }
          }}
        />
        <button type="button" className="btn-cyber text-xs py-1 px-3"
          disabled={transcribe.isPending}
          onClick={() => recording ? recorderRef.current?.stop() : void startRecording()}>
          {recording ? "Stop recording" : "Record audio"}
        </button>
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

      {recordingError && <p className="text-[10px] text-red-400">{recordingError}</p>}
      {audioUrl && <audio ref={playerRef} controls src={audioUrl} className="w-full" />}

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
                  {audioUrl && <button type="button" onClick={() => {
                    if (playerRef.current) {
                      playerRef.current.currentTime = segment.start;
                      void playerRef.current.play();
                    }
                  }}>Play from segment</button>}
                </div>
                <label className="block text-[9px] text-slate-500">
                  Speaker
                  <input aria-label={`Speaker for segment ${segment.index + 1}`}
                    value={speakers[segment.index] ?? segment.speaker ?? ""}
                    onChange={(e) => setSpeakers((prev) => ({ ...prev, [segment.index]: e.target.value }))}
                    className="input-cyber ml-2 text-[10px]" />
                </label>
                <textarea
                  value={value}
                  maxLength={4000}
                  aria-label={`Segment ${segment.index + 1}`}
                  onChange={(e) =>
                    setEdits((prev) => ({ ...prev, [segment.index]: e.target.value }))
                  }
                  className="input-cyber w-full text-[11px] min-h-[48px]"
                />
                {value.trim().length > 4000 && (
                  <p className="text-[10px] text-amber-400">Shorten this segment to 4000 characters before queueing.</p>
                )}
                <div className="flex items-center justify-end gap-2">
                  {segment.index in queued && (
                    <span className="text-[9px] text-emerald-400">
                      Entry queued ({queuedCount} new proposal{queuedCount === 1 ? "" : "s"})
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => queue.mutate(segment)}
                    disabled={queue.isPending || !value.trim() || value.trim().length > 4000}
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
          The segment could not be queued. Check the active recording and try again.
        </p>
      )}
    </div>
  );
}

export default AudioTranscriptPanel;
