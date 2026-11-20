// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConnectionBanner } from "./ConnectionBanner";

describe("ConnectionBanner", () => {
  it("renders nothing while connected", () => {
    const { container } = render(<ConnectionBanner status="connected" />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the reconnecting banner with backoff copy", () => {
    render(<ConnectionBanner status="reconnecting" />);
    const banner = screen.getByTestId("connection-banner");
    expect(banner).toHaveAttribute("data-status", "reconnecting");
    expect(banner).toHaveTextContent(/reconnecting/i);
    expect(banner).toHaveTextContent(/backoff/i);
    expect(banner).toHaveAttribute("aria-live", "polite");
  });

  it("shows a connecting banner while the socket handshakes", () => {
    render(<ConnectionBanner status="connecting" />);
    expect(screen.getByTestId("connection-banner")).toHaveTextContent(/connecting/i);
  });

  it("shows the disconnected state distinctly", () => {
    render(<ConnectionBanner status="disconnected" />);
    const banner = screen.getByTestId("connection-banner");
    expect(banner).toHaveAttribute("data-status", "disconnected");
    expect(banner).toHaveTextContent(/disconnected/i);
  });
});
