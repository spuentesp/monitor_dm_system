// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GraduateDialog } from "./GraduateDialog";
import { chatApi, universesApi } from "@/lib/api";
import { lightRpApi } from "@/lib/lightRpApi";
import type { StandaloneCharacter } from "@/lib/types";

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const char = {
  id: "c-1",
  name: "Wisp",
  description: "A fox-spirit guide.",
  avatar_url: null,
  personality: "playful",
  gm_notes: "",
  first_message: "Well met.",
  is_ooc_persona: false,
  entity_id: "e-1",
  default_universe_id: null,
  versions: [],
  memory_count: 3,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
} as StandaloneCharacter;

const prepareResult = {
  character_id: "c-1",
  universe_id: "u-1",
  entity_id: "e-1",
  version_id: "v-1",
  start_options: [{ option_id: "storm", title: "The storm at Blackreef", summary: "A storm rolls in." }],
  start_options_source: "canon",
  question: "How would you like to begin?",
  suggested_answers: ["The storm at Blackreef", "Surprise me"],
};

const graduateResult = {
  character_id: "c-1",
  universe_id: "u-1",
  entity_id: "e-1",
  version_id: "v-1",
  chosen: { option_id: "storm", option_title: "The storm at Blackreef", is_surprise: false, free_answer: "" },
  story_premise: "A storm rolls in.",
  memories_carried: 4,
  session_create: {
    title: "Wisp — new campaign",
    mode: "autonomous_gm",
    universe_id: "u-1",
    character_id: "e-1",
    persona_id: "p-1",
    story_premise: "A storm rolls in.",
    tone: "dramatic",
  },
};

function renderDialog(onGraduated = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <GraduateDialog character={char} personaId="p-1" onGraduated={onGraduated} onClose={() => {}} />
    </QueryClientProvider>,
  );
  return onGraduated;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(universesApi, "listUniverses").mockResolvedValue([{ id: "u-1", name: "Grey Harbour" }] as never);
});

describe("GraduateDialog — start a campaign with this character", () => {
  it("prepares the guided start in the chosen universe", async () => {
    const prepare = vi.spyOn(lightRpApi, "graduatePrepare").mockResolvedValue(prepareResult);
    const user = userEvent.setup();
    renderDialog();

    await user.click(await screen.findByRole("button", { name: /continue/i }));

    await waitFor(() => expect(prepare).toHaveBeenCalledWith("c-1", { universe_id: "u-1" }));
    expect(await screen.findByText("How would you like to begin?")).toBeInTheDocument();
  });

  it("graduates with character, persona and memories, then opens the guided-start session", async () => {
    vi.spyOn(lightRpApi, "graduatePrepare").mockResolvedValue(prepareResult);
    const graduate = vi.spyOn(lightRpApi, "graduateToCampaign").mockResolvedValue(graduateResult);
    const createSession = vi
      .spyOn(chatApi, "createSession")
      .mockResolvedValue({ id: "sess-1" } as never);
    const user = userEvent.setup();
    const onGraduated = renderDialog();

    await user.click(await screen.findByRole("button", { name: /continue/i }));
    await user.click(await screen.findByRole("button", { name: "The storm at Blackreef" }));
    await user.click(await screen.findByRole("button", { name: /start campaign/i }));

    await waitFor(() =>
      expect(graduate).toHaveBeenCalledWith("c-1", {
        universe_id: "u-1",
        persona_character_id: "p-1",
        start_answer: "The storm at Blackreef",
        start_options: prepareResult.start_options,
        question_text: "How would you like to begin?",
      }),
    );
    await waitFor(() =>
      expect(createSession).toHaveBeenCalledWith(graduateResult.session_create),
    );
    await waitFor(() => expect(onGraduated).toHaveBeenCalledWith({ id: "sess-1" }));
  });
});
