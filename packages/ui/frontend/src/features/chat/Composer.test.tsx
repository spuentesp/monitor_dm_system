// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer, type QuickAction } from "./Composer";

describe("Composer", () => {
  it("renders a textarea + send button", () => {
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSubmit={() => {}}
        status="connected"
      />,
    );
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send message/i })).toBeInTheDocument();
  });

  it("disables the send button when value is empty", () => {
    render(
      <Composer value="" onChange={() => {}} onSubmit={() => {}} status="connected" />,
    );
    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();
  });

  it("enables the send button when value is non-empty", () => {
    render(
      <Composer value="hello" onChange={() => {}} onSubmit={() => {}} status="connected" />,
    );
    expect(screen.getByRole("button", { name: /send message/i })).not.toBeDisabled();
  });

  it("disables the send button while isTyping", () => {
    render(
      <Composer
        value="hello"
        onChange={() => {}}
        onSubmit={() => {}}
        status="connected"
        isTyping
      />,
    );
    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();
  });

  it("Enter calls onSubmit with trimmed value and clears the textarea via onChange", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const onChange = vi.fn();
    render(
      <Composer value="  hi  " onChange={onChange} onSubmit={onSubmit} status="connected" />,
    );

    await user.click(screen.getByRole("textbox"));
    await user.keyboard("{Enter}");

    expect(onSubmit).toHaveBeenCalledWith("hi");
    // Composer calls onChange("") to clear after submit.
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("Shift+Enter inserts a newline instead of submitting", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <Composer value="line1" onChange={() => {}} onSubmit={onSubmit} status="connected" />,
    );

    await user.click(screen.getByRole("textbox"));
    await user.keyboard("{Shift>}{Enter}{/Shift}");

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("quick-action 'fill' calls onChange with the action text", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const quickActions: QuickAction[] = [
      { label: "Look around", onClick: "fill", text: "I look around" },
    ];
    render(
      <Composer value="" onChange={onChange} onSubmit={() => {}} status="connected" quickActions={quickActions} />,
    );

    await user.click(screen.getByRole("button", { name: /Look around/i }));
    expect(onChange).toHaveBeenCalledWith("I look around");
  });

  it("quick-action 'submit' calls onSubmit with the action text", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const quickActions: QuickAction[] = [
      { label: "Retry last", onClick: "submit", text: "previous action" },
    ];
    render(
      <Composer value="" onChange={() => {}} onSubmit={onSubmit} status="connected" quickActions={quickActions} />,
    );

    await user.click(screen.getByRole("button", { name: /Retry last/i }));
    expect(onSubmit).toHaveBeenCalledWith("previous action");
  });

  it("quick-action with disabled=true is inert", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const quickActions: QuickAction[] = [
      { label: "Disabled action", onClick: "submit", text: "x", disabled: true },
    ];
    render(
      <Composer value="" onChange={() => {}} onSubmit={onSubmit} status="connected" quickActions={quickActions} />,
    );

    await user.click(screen.getByRole("button", { name: /Disabled action/i }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disconnected status surfaces the StatusPill when onReconnect is provided", () => {
    render(
      <Composer value="" onChange={() => {}} onSubmit={() => {}} status="disconnected" onReconnect={() => {}} />,
    );
    // The pill contains a "Disconnected — retry" string with a button.
    expect(screen.getByText(/Disconnected/)).toBeInTheDocument();
  });

  it("renders extraTop slot above the chips", () => {
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSubmit={() => {}}
        status="connected"
        extraTop={<div data-testid="extra-top">Starter probes</div>}
      />,
    );
    expect(screen.getByTestId("extra-top")).toBeInTheDocument();
  });
});