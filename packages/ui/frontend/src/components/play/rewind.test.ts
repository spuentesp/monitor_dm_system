// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { Message, RewindResult } from "@/lib/types";

import {
  REWIND_FAILED_MESSAGE,
  removeLastExchange,
  rewindErrorMessage,
  rewindLastExchange,
} from "./rewind";

function msg(id: string, content: string): Message {
  return {
    id,
    session_id: "s1",
    role: "player",
    content,
    timestamp: new Date().toISOString(),
    metadata: {},
  };
}

describe("removeLastExchange", () => {
  it("drops the last `removed` messages", () => {
    const messages = [msg("1", "a"), msg("2", "b"), msg("3", "c"), msg("4", "d")];
    expect(removeLastExchange(messages, 2).map((m) => m.id)).toEqual(["1", "2"]);
  });

  it("is a no-op for 0 / negative / non-finite counts", () => {
    const messages = [msg("1", "a")];
    expect(removeLastExchange(messages, 0)).toBe(messages);
    expect(removeLastExchange(messages, -3)).toBe(messages);
    expect(removeLastExchange(messages, Number.NaN)).toBe(messages);
  });

  it("clamps an oversized count to an empty transcript", () => {
    const messages = [msg("1", "a"), msg("2", "b")];
    expect(removeLastExchange(messages, 99)).toEqual([]);
  });
});

describe("rewindErrorMessage", () => {
  it("surfaces the backend's 409 canon refusal detail", () => {
    const err = new ApiError(
      409,
      JSON.stringify({ detail: "The GM's last turn already changed canon; it can't be rewound." }),
    );
    expect(rewindErrorMessage(err)).toBe(
      "The GM's last turn already changed canon; it can't be rewound.",
    );
  });

  it("surfaces the turn-in-flight 409 detail", () => {
    const err = new ApiError(
      409,
      JSON.stringify({ detail: "A GM turn is still in flight — wait for it to finish before rewinding." }),
    );
    expect(rewindErrorMessage(err)).toMatch(/still in flight/);
  });

  it("falls back to the generic copy for an unparsable 409 body", () => {
    expect(rewindErrorMessage(new ApiError(409, "gateway said what"))).toBe(REWIND_FAILED_MESSAGE);
  });

  it("passes through other errors via errorMessage", () => {
    expect(rewindErrorMessage(new Error("boom"))).toBe("boom");
    expect(rewindErrorMessage("plain")).toBe("plain");
  });
});

describe("rewindLastExchange", () => {
  const result: RewindResult = { removed: 2, last_player_text: "I open the door." };

  it("returns the removed player text and applies the result on success", async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const text = await rewindLastExchange({
      disabled: false,
      rewind: vi.fn().mockResolvedValue(result),
      onSuccess,
      onError,
    });
    expect(text).toBe("I open the door.");
    expect(onSuccess).toHaveBeenCalledWith(result);
    expect(onError).not.toHaveBeenCalled();
  });

  it("does nothing while a turn is in flight", async () => {
    const rewind = vi.fn();
    const onSuccess = vi.fn();
    const text = await rewindLastExchange({
      disabled: true,
      rewind,
      onSuccess,
      onError: vi.fn(),
    });
    expect(text).toBeNull();
    expect(rewind).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("reports the parsed refusal and returns null on failure", async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const text = await rewindLastExchange({
      disabled: false,
      rewind: vi.fn().mockRejectedValue(new ApiError(409, JSON.stringify({ detail: "nope" }))),
      onSuccess,
      onError,
    });
    expect(text).toBeNull();
    expect(onError).toHaveBeenCalledWith("nope");
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
