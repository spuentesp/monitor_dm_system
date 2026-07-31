import type { Page } from "@playwright/test";

interface Frame {
  dir: "send" | "recv";
  t: number;
  data: Record<string, unknown> | string;
}

interface TurnMatrix {
  id: string;
  events: string[];
}

interface SpyHandle {
  matrix(): Promise<TurnMatrix[]>;
  frames(): Promise<Frame[]>;
}

/**
 * Install a WebSocket subclass via addInitScript so the page records
 * every send/recv frame. The `matrix()` accessor groups frames by
 * `message_id` and returns the per-turn event timeline, which is the
 * single artifact we assert on (see roleplay.spec.ts R-01).
 *
 * Must be called BEFORE `page.goto(...)` — addInitScript runs on every
 * new document, so installing it later misses the socket the React
 * effect opens on mount.
 */
export async function attachWsSpy(page: Page): Promise<SpyHandle> {
  await page.addInitScript(() => {
    interface SpyWindow {
      __wsSpy?: { frames: Frame[] };
    }
    const w = window as unknown as SpyWindow;
    w.__wsSpy = { frames: [] };
    const OrigWS = window.WebSocket;
    const spyFrames = w.__wsSpy.frames;
    // Patching the global with a subclass preserves `new WebSocket(...)`
    // semantics; the prototype chain still satisfies `instanceof`.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).WebSocket = class extends OrigWS {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      constructor(url: any, protocols?: any) {
        super(url, protocols);
        const sock = this;
        const origSend = sock.send.bind(sock);
        sock.send = (data: string | ArrayBufferLike | Blob | ArrayBufferView) => {
          spyFrames.push({ dir: "send", t: Date.now(), data: safeParse(data) });
          return origSend(data);
        };
        sock.addEventListener("message", (ev: MessageEvent) => {
          spyFrames.push({ dir: "recv", t: Date.now(), data: safeParse(ev.data) });
        });
      }
    };
    function safeParse(d: unknown): Record<string, unknown> | string {
      if (typeof d !== "string") return String(d);
      try {
        return JSON.parse(d) as Record<string, unknown>;
      } catch {
        return d;
      }
    }
  });

  return {
    async matrix() {
      return page.evaluate(() => {
        interface SpyWindow2 {
          __wsSpy: { frames: Frame[] };
        }
        const w = window as unknown as SpyWindow2;
        const frames = w.__wsSpy.frames;
        const byMsg = new Map<string, TurnMatrix>();
        for (const f of frames) {
          if (f.dir !== "recv") continue;
          const data = typeof f.data === "object" ? f.data : {};
          const id =
            (data as { message_id?: string }).message_id ?? "_global";
          const ev = byMsg.get(id) ?? { id, events: [] };
          const t = (data as { type?: string }).type;
          if (t) ev.events.push(t);
          byMsg.set(id, ev);
        }
        return [...byMsg.values()];
      });
    },
    async frames() {
      return page.evaluate(() => {
        interface SpyWindow2 {
          __wsSpy: { frames: Frame[] };
        }
        const w = window as unknown as SpyWindow2;
        return w.__wsSpy.frames;
      });
    },
  };
}