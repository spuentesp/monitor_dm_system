// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TemplateEditor } from "./TemplateEditor";
import { characterTemplatesApi } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  characterTemplatesApi: { create: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));

const template = {
  template_id: "tpl-1", name: "Varys", concept: "Spy", personality: "Patient",
  backstory_beats: ["Lost a city"], voice: "Quiet", portrait_url: "https://example.com/v.png",
  first_message: "Hello", gm_notes: "Secret", usage_count: 0,
};

function renderEditor(onCreated = vi.fn(), onDeleted = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><TemplateEditor template={template} onClose={vi.fn()} onCreated={onCreated} onDeleted={onDeleted} /></QueryClientProvider>);
  return { onCreated, onDeleted };
}

beforeEach(() => vi.resetAllMocks());

describe("TemplateEditor", () => {
  it("updates an existing template and clears its portrait", async () => {
    const updated = { ...template, portrait_url: null, first_message: "Greetings" };
    vi.mocked(characterTemplatesApi.update).mockResolvedValue(updated);
    const { onCreated } = renderEditor();
    fireEvent.change(screen.getByLabelText("Portrait URL"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("First message"), { target: { value: "Greetings" } });
    fireEvent.click(screen.getByRole("button", { name: "Save template" }));
    await waitFor(() => expect(characterTemplatesApi.update).toHaveBeenCalledWith("tpl-1", expect.objectContaining({ portrait_url: null, first_message: "Greetings" })));
    expect(onCreated).toHaveBeenCalledWith(updated);
  });

  it("deletes only after confirmation", async () => {
    vi.mocked(characterTemplatesApi.remove).mockResolvedValue(undefined);
    const { onDeleted } = renderEditor();
    fireEvent.click(screen.getByRole("button", { name: "Delete template" }));
    expect(characterTemplatesApi.remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("tpl-1"));
    expect(characterTemplatesApi.remove).toHaveBeenCalledWith("tpl-1");
  });
});
