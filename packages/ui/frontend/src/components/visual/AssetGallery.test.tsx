// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  AssetGallery,
  PendingAssetPreview,
  deriveReferenceConditioningMode,
} from "./AssetGallery";
import * as api from "@/lib/api";
import type { GeneratedAsset } from "@/lib/types";

vi.mock("@/components/NotificationProvider", () => ({
  useNotify: () => ({ notify: vi.fn() }),
}));

function asset(overrides: Partial<GeneratedAsset>): GeneratedAsset {
  return {
    asset_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    asset_type: "portrait",
    minio_key: "assets/portrait/character-c-1/x.png",
    content_type: "image/png",
    byte_size: 1234,
    character_id: "c-1",
    entity_id: null,
    universe_id: null,
    story_id: null,
    scene_id: null,
    conversation_id: null,
    source_message_ids: [],
    visual_identity_id: null,
    visual_identity_version: null,
    canon_fact_ids: [],
    prompt: "a fox-spirit guide",
    negative_prompt: null,
    prompt_warnings: [],
    reference_asset_ids: [],
    provider_id: "fake-provider",
    provider_model: "fake-image-1",
    provider_capabilities: {},
    trigger: "user",
    moderation_status: "provider_default",
    approval_status: "pending",
    reference_status: "none",
    approved_by: null,
    approved_at: null,
    estimated_cost_usd: null,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
    ...overrides,
  };
}

const pendingPortrait = asset({ asset_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1" });
const approvedPortrait = asset({
  asset_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2",
  approval_status: "approved",
});
const rejectedScene = asset({
  asset_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3",
  asset_type: "scene",
  character_id: null,
  approval_status: "rejected",
});

function renderGallery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("AssetGallery", () => {
  it("lists assets for the scope and renders thumbnails via the file endpoint", async () => {
    const list = vi.spyOn(api.imageApi, "listAssets").mockResolvedValue([approvedPortrait]);
    renderGallery(<AssetGallery filter={{ character_id: "c-1" }} />);

    const img = await screen.findByRole("img");
    expect(img).toHaveAttribute(
      "src",
      api.apiUrl("/image/assets/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2/file"),
    );
    expect(list).toHaveBeenCalledWith(
      expect.objectContaining({ character_id: "c-1", include_rejected: false }),
    );
  });

  it("renders pending assets as previews with approve/reject actions", async () => {
    vi.spyOn(api.imageApi, "listAssets").mockResolvedValue([pendingPortrait]);
    renderGallery(<AssetGallery filter={{ character_id: "c-1" }} />);

    expect(await screen.findByText(/pending approval/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^approve$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeInTheDocument();
  });

  it("approves with use_as_avatar and a primary reference role", async () => {
    vi.spyOn(api.imageApi, "listAssets").mockResolvedValue([pendingPortrait]);
    const approve = vi
      .spyOn(api.imageApi, "approveAsset")
      .mockResolvedValue({ ...pendingPortrait, approval_status: "approved" });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    renderGallery(
      <AssetGallery filter={{ character_id: "c-1" }} allowAvatar onChanged={onChanged} />,
    );

    await screen.findByText(/pending approval/i);
    await user.click(screen.getByLabelText(/use as avatar/i));
    await user.selectOptions(screen.getByLabelText(/reference status/i), "primary");
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    await waitFor(() =>
      expect(approve).toHaveBeenCalledWith(pendingPortrait.asset_id, {
        use_as_avatar: true,
        reference_status: "primary",
      }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("approves with a supporting reference role", async () => {
    vi.spyOn(api.imageApi, "listAssets").mockResolvedValue([pendingPortrait]);
    const approve = vi
      .spyOn(api.imageApi, "approveAsset")
      .mockResolvedValue({ ...pendingPortrait, approval_status: "approved" });
    const user = userEvent.setup();
    renderGallery(<AssetGallery filter={{ character_id: "c-1" }} />);

    await screen.findByText(/pending approval/i);
    await user.selectOptions(screen.getByLabelText(/reference status/i), "supporting");
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    await waitFor(() =>
      expect(approve).toHaveBeenCalledWith(pendingPortrait.asset_id, {
        use_as_avatar: false,
        reference_status: "supporting",
      }),
    );
  });

  it("rejects a pending asset", async () => {
    vi.spyOn(api.imageApi, "listAssets").mockResolvedValue([pendingPortrait]);
    const reject = vi
      .spyOn(api.imageApi, "rejectAsset")
      .mockResolvedValue({ ...pendingPortrait, approval_status: "rejected" });
    const user = userEvent.setup();
    renderGallery(<AssetGallery filter={{ character_id: "c-1" }} />);

    await screen.findByText(/pending approval/i);
    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    await waitFor(() => expect(reject).toHaveBeenCalledWith(pendingPortrait.asset_id));
  });

  it("hides rejected assets by default and shows them on demand", async () => {
    const list = vi
      .spyOn(api.imageApi, "listAssets")
      .mockResolvedValueOnce([approvedPortrait])
      .mockResolvedValueOnce([approvedPortrait, rejectedScene]);
    const user = userEvent.setup();
    renderGallery(<AssetGallery filter={{ character_id: "c-1" }} />);

    await screen.findByRole("img");
    expect(list).toHaveBeenCalledWith(
      expect.objectContaining({ include_rejected: false }),
    );
    expect(screen.queryByText(/^rejected$/i)).not.toBeInTheDocument();

    await user.click(screen.getByLabelText(/show rejected/i));
    await waitFor(() =>
      expect(list).toHaveBeenCalledWith(expect.objectContaining({ include_rejected: true })),
    );
    expect(await screen.findByText(/^rejected$/i)).toBeInTheDocument();
    // Rejected assets carry no review actions.
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
  });

  it("does not offer use-as-avatar for scene assets", async () => {
    vi.spyOn(api.imageApi, "listAssets").mockResolvedValue([
      asset({
        asset_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa4",
        asset_type: "scene",
        character_id: null,
      }),
    ]);
    renderGallery(<AssetGallery filter={{ conversation_id: "conv-1" }} allowAvatar />);

    await screen.findByText(/pending approval/i);
    expect(screen.queryByLabelText(/use as avatar/i)).not.toBeInTheDocument();
  });

  it("shows a filtered empty state", async () => {
    vi.spyOn(api.imageApi, "listAssets").mockResolvedValue([]);
    renderGallery(<AssetGallery filter={{ character_id: "c-1" }} />);

    expect(await screen.findByText(/no images yet/i)).toBeInTheDocument();
  });
});

describe("PendingAssetPreview", () => {
  it("renders the generated image as a pending preview with actions", () => {
    render(
      <PendingAssetPreview
        assetId={pendingPortrait.asset_id}
        imageUrl="https://minio.example.com/p.png"
      />,
    );

    expect(screen.getByRole("img")).toHaveAttribute("src", "https://minio.example.com/p.png");
    expect(screen.getByText(/pending approval/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^approve$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeInTheDocument();
  });

  it("approving calls the approve endpoint and reports the decision", async () => {
    const approve = vi
      .spyOn(api.imageApi, "approveAsset")
      .mockResolvedValue({ ...pendingPortrait, approval_status: "approved" });
    const onDecided = vi.fn();
    const user = userEvent.setup();
    render(
      <PendingAssetPreview
        assetId={pendingPortrait.asset_id}
        imageUrl="https://minio.example.com/p.png"
        allowAvatar
        onDecided={onDecided}
      />,
    );

    await user.click(screen.getByLabelText(/use as avatar/i));
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    await waitFor(() =>
      expect(approve).toHaveBeenCalledWith(pendingPortrait.asset_id, {
        use_as_avatar: true,
        reference_status: "none",
      }),
    );
    await waitFor(() => expect(onDecided).toHaveBeenCalledWith("approved"));
  });

  it("rejecting calls the reject endpoint and reports the decision", async () => {
    const reject = vi
      .spyOn(api.imageApi, "rejectAsset")
      .mockResolvedValue({ ...pendingPortrait, approval_status: "rejected" });
    const onDecided = vi.fn();
    const user = userEvent.setup();
    render(
      <PendingAssetPreview
        assetId={pendingPortrait.asset_id}
        imageUrl="https://minio.example.com/p.png"
        onDecided={onDecided}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    await waitFor(() => expect(reject).toHaveBeenCalledWith(pendingPortrait.asset_id));
    await waitFor(() => expect(onDecided).toHaveBeenCalledWith("rejected"));
  });

  it("surfaces a text-only fallback badge when the response carries that warning", () => {
    render(
      <PendingAssetPreview
        assetId={pendingPortrait.asset_id}
        imageUrl="https://minio.example.com/p.png"
        warnings={[
          "text-only fallback: provider does not consume reference images; dropped 2 approved reference(s) at the orchestrator.",
        ]}
      />,
    );
    expect(screen.getByTestId("ref-mode-text-only")).toHaveTextContent(/text-only fallback/i);
  });

  it("surfaces a reference-conditioning-active badge when the response carries that warning", () => {
    render(
      <PendingAssetPreview
        assetId={pendingPortrait.asset_id}
        imageUrl="https://minio.example.com/p.png"
        warnings={["reference conditioning active: sent 2 of 2 approved reference(s) to ref-capable-test."]}
        referenceAssetIds={["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]}
      />,
    );
    expect(screen.getByTestId("ref-mode-active")).toHaveTextContent(/reference conditioning active/i);
  });

  it("defaults to text-only fallback when neither warnings nor references are present", () => {
    render(
      <PendingAssetPreview
        assetId={pendingPortrait.asset_id}
        imageUrl="https://minio.example.com/p.png"
      />,
    );
    expect(screen.getByTestId("ref-mode-text-only")).toBeInTheDocument();
  });
});

describe("deriveReferenceConditioningMode", () => {
  it("returns 'reference' when the active warning is present", () => {
    expect(
      deriveReferenceConditioningMode(
        ["reference conditioning active: sent 1 of 1 approved reference(s) to x."],
        ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
      ),
    ).toBe("reference");
  });

  it("returns 'text-only' when the fallback warning is present", () => {
    expect(
      deriveReferenceConditioningMode(
        ["text-only fallback: provider does not consume reference images; dropped 3 approved reference(s) at the orchestrator."],
        ["a", "b", "c"],
      ),
    ).toBe("text-only");
  });

  it("falls back to 'reference' from provenance when warnings are absent", () => {
    expect(deriveReferenceConditioningMode([], ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"])).toBe(
      "reference",
    );
  });

  it("falls back to 'text-only' when neither warnings nor references are set", () => {
    expect(deriveReferenceConditioningMode([], [])).toBe("text-only");
  });

  it("active warning wins over the fallback warning when both are present", () => {
    expect(
      deriveReferenceConditioningMode(
        [
          "reference conditioning active: sent 1 of 1 approved reference(s) to x.",
          "text-only fallback: provider does not consume reference images; dropped 0 approved reference(s) at the orchestrator.",
        ],
        ["a"],
      ),
    ).toBe("reference");
  });
});
