// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CharacterCreateDialog } from "./CharacterCreateDialog";
import * as api from "@/lib/api";

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

describe("CharacterCreateDialog", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a persona card and reports it through onCreated", async () => {
    const create = vi
      .spyOn(api.entitiesApi, "createStandaloneCharacter")
      .mockResolvedValue({ id: "c-new" } as never);
    const onCreated = vi.fn();
    const user = userEvent.setup();
    render(<CharacterCreateDialog onCreated={onCreated} onClose={() => {}} />);

    await user.type(screen.getByPlaceholderText(/character's name|character name/i), "Rin");
    await user.click(screen.getByRole("checkbox"));
    await user.type(screen.getByPlaceholderText(/who they are/i), "A courier with a loud laugh.");
    await user.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Rin",
        is_ooc_persona: true,
        description: "A courier with a loud laugh.",
      }),
    );
  });

  it("keeps Create disabled until a name is entered", async () => {
    vi.spyOn(api.entitiesApi, "createStandaloneCharacter").mockResolvedValue({ id: "c" } as never);
    render(<CharacterCreateDialog onCreated={() => {}} onClose={() => {}} />);
    expect(screen.getByRole("button", { name: /create/i })).toBeDisabled();
  });
});
