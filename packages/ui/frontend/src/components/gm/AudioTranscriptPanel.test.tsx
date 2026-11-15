// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { gmAudioApi } from "@/lib/gm-audio-api";
import { AudioTranscriptPanel } from "./AudioTranscriptPanel";

function renderPanel(universeId: string | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AudioTranscriptPanel universeId={universeId} />
    </QueryClientProvider>,
  );
}

const TRANSCRIPT = {
  transcript_id: "tr-1",
  universe_id: "u-1",
  provider: "fake-asr",
  model: "fake-model",
  text: "The council met at dusk.",
  language: "en",
  duration: 3,
  audio_key: "audio/u-1/gm/take.wav",
  segments: [
    {
      id: "seg-1",
      index: 0,
      start: 0,
      end: 3,
      text: "The council met at dusk.",
      speaker: null,
      reviewed: false,
    },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } })),
  ) as unknown as typeof fetch;
  vi.spyOn(gmAudioApi, "transcribe").mockResolvedValue(TRANSCRIPT);
  vi.spyOn(gmAudioApi, "queueSegment").mockResolvedValue({
    transcript_id: "tr-1",
    segment_index: 0,
    proposal_ids: ["p-1"],
  });
});

describe("AudioTranscriptPanel (CF-10)", () => {
  it("prompts for a universe when none is selected", () => {
    renderPanel(null);
    expect(screen.getByText(/select a universe to record a session/i)).toBeInTheDocument();
  });

  it("uploads a recording and shows the transcript", async () => {
    renderPanel("u-1");
    const file = new File(["audio"], "take.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText("Recording"), file);

    expect(await screen.findByDisplayValue("The council met at dusk.")).toBeInTheDocument();
    expect(screen.getByText(/transcribed by fake-asr/)).toBeInTheDocument();
  });

  it("lets the GM fix what the transcriber got wrong", async () => {
    renderPanel("u-1");
    const file = new File(["audio"], "take.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText("Recording"), file);

    const field = await screen.findByDisplayValue("The council met at dusk.");
    await userEvent.clear(field);
    await userEvent.type(field, "The council met at dawn.");

    expect(screen.getByDisplayValue("The council met at dawn.")).toBeInTheDocument();
  });

  it("queues a segment with the corrected text", async () => {
    renderPanel("u-1");
    const file = new File(["audio"], "take.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText("Recording"), file);

    const field = await screen.findByDisplayValue("The council met at dusk.");
    await userEvent.clear(field);
    await userEvent.type(field, "The council met at dawn.");
    await userEvent.type(screen.getByLabelText("Speaker for segment 1"), "Mira");
    await userEvent.click(screen.getByLabelText("Queue segment 1"));

    await waitFor(() => expect(gmAudioApi.queueSegment).toHaveBeenCalled());
    expect(vi.mocked(gmAudioApi.queueSegment).mock.calls[0]).toEqual([
      "tr-1",
      0,
      "The council met at dawn.",
      "Mira",
    ]);
    expect(await screen.findByText(/Entry queued \(1 new proposal\)/)).toBeInTheDocument();
  });

  it("says when the recording has no speech", async () => {
    vi.spyOn(gmAudioApi, "transcribe").mockResolvedValue({ ...TRANSCRIPT, segments: [] });
    renderPanel("u-1");
    const file = new File(["audio"], "take.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText("Recording"), file);

    expect(await screen.findByText(/no speech in it/i)).toBeInTheDocument();
  });

  it("reports a transcription that failed", async () => {
    vi.spyOn(gmAudioApi, "transcribe").mockRejectedValue(new Error("no backend"));
    renderPanel("u-1");
    const file = new File(["audio"], "take.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText("Recording"), file);

    expect(await screen.findByText(/could not be transcribed/i)).toBeInTheDocument();
  });
});
