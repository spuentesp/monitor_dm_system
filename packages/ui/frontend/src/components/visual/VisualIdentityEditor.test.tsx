// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VisualIdentityEditor } from "./VisualIdentityEditor";
import * as api from "@/lib/api";
import type { VisualIdentity } from "@/lib/types";

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

const draftIdentity: VisualIdentity = {
  identity_id: "11111111-1111-1111-1111-111111111111",
  character_id: "c-1",
  entity_id: null,
  universe_id: null,
  version: 2,
  description: "A fox-spirit guide.",
  species_or_type: "fox spirit",
  apparent_age: "young adult",
  build: "slight",
  hair: "silver, shoulder-length",
  eyes: "ember",
  skin_or_surface: "pale",
  signature_attire: "travel cloak",
  distinguishing_features: ["fox ears"],
  palette: ["silver", "ember orange"],
  style_hint: "watercolor",
  source: "manual",
  approved_reference_asset_ids: [],
  status: "draft",
  decision_proposal_id: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-30T00:00:00Z",
};

const canonIdentity: VisualIdentity = {
  ...draftIdentity,
  identity_id: "22222222-2222-2222-2222-222222222222",
  entity_id: "e-1",
  universe_id: "u-1",
  version: 3,
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("VisualIdentityEditor", () => {
  it("loads the current draft identity into the form", async () => {
    const get = vi
      .spyOn(api.imageApi, "getCurrentVisualIdentity")
      .mockResolvedValue(draftIdentity);
    render(<VisualIdentityEditor characterId="c-1" />);

    expect(await screen.findByDisplayValue("silver, shoulder-length")).toBeInTheDocument();
    expect(screen.getByDisplayValue("fox spirit")).toBeInTheDocument();
    expect(screen.getByDisplayValue("travel cloak")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(
      expect.objectContaining({ character_id: "c-1", status: "draft" }),
    );
  });

  it("falls back to the approved identity when no draft exists", async () => {
    const get = vi
      .spyOn(api.imageApi, "getCurrentVisualIdentity")
      .mockRejectedValueOnce(new api.ApiError(404, "no draft"))
      .mockResolvedValueOnce({ ...draftIdentity, status: "approved", version: 1 });
    render(<VisualIdentityEditor characterId="c-1" />);

    expect(await screen.findByDisplayValue("silver, shoulder-length")).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenLastCalledWith(
      expect.objectContaining({ character_id: "c-1", status: "approved" }),
    );
  });

  it("shows an empty state when no identity exists for the anchor", async () => {
    vi.spyOn(api.imageApi, "getCurrentVisualIdentity").mockRejectedValue(
      new api.ApiError(404, "No visual identity found for this anchor"),
    );
    render(<VisualIdentityEditor characterId="c-1" />);

    expect(await screen.findByText(/no visual identity yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save draft/i })).not.toBeInTheDocument();
  });

  it("saves edits as a new draft version", async () => {
    vi.spyOn(api.imageApi, "getCurrentVisualIdentity").mockResolvedValue(draftIdentity);
    const updated: VisualIdentity = { ...draftIdentity, version: 3, hair: "black, cropped" };
    const put = vi.spyOn(api.imageApi, "updateVisualIdentity").mockResolvedValue(updated);
    const onSaved = vi.fn();
    const user = userEvent.setup();
    render(<VisualIdentityEditor characterId="c-1" onSaved={onSaved} />);

    const hair = await screen.findByLabelText(/^hair$/i);
    await user.clear(hair);
    await user.type(hair, "black, cropped");
    await user.click(screen.getByRole("button", { name: /save draft/i }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith(
        expect.objectContaining({
          identity_id: draftIdentity.identity_id,
          expected_version: 2,
          hair: "black, cropped",
          eyes: "ember",
        }),
      ),
    );
    expect(onSaved).toHaveBeenCalledWith(updated);
    expect(await screen.findByText(/saved as draft/i)).toBeInTheDocument();
  });

  it("surfaces a 409 conflict and offers to reload the latest version", async () => {
    const get = vi
      .spyOn(api.imageApi, "getCurrentVisualIdentity")
      .mockResolvedValue(draftIdentity);
    vi.spyOn(api.imageApi, "updateVisualIdentity").mockRejectedValue(
      new api.ApiError(409, "expected version 2 is no longer current"),
    );
    const user = userEvent.setup();
    render(<VisualIdentityEditor characterId="c-1" />);

    await screen.findByDisplayValue("silver, shoulder-length");
    await user.click(screen.getByRole("button", { name: /save draft/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/newer version/i);
    // Reload pulls the identity again and clears the conflict.
    await user.click(screen.getByRole("button", { name: /reload/i }));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(await screen.findByDisplayValue("silver, shoulder-length")).toBeInTheDocument();
  });

  it("offers Submit for review for canon-anchored identities and shows the result", async () => {
    vi.spyOn(api.imageApi, "getCurrentVisualIdentity").mockResolvedValue(canonIdentity);
    const put = vi
      .spyOn(api.imageApi, "updateVisualIdentity")
      .mockResolvedValue({ ...canonIdentity, version: 4 });
    const user = userEvent.setup();
    render(<VisualIdentityEditor characterId="c-1" entityId="e-1" universeId="u-1" />);

    await screen.findByDisplayValue("silver, shoulder-length");
    await user.click(screen.getByRole("button", { name: /submit for review/i }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith(
        expect.objectContaining({
          identity_id: canonIdentity.identity_id,
          expected_version: 3,
        }),
      ),
    );
    expect(await screen.findByText(/canonkeeper review/i)).toBeInTheDocument();
  });

  it("does not offer Submit for review for card-default identities", async () => {
    vi.spyOn(api.imageApi, "getCurrentVisualIdentity").mockResolvedValue(draftIdentity);
    render(<VisualIdentityEditor characterId="c-1" />);

    await screen.findByDisplayValue("silver, shoulder-length");
    expect(screen.queryByRole("button", { name: /submit for review/i })).not.toBeInTheDocument();
  });
});
