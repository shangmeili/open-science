// @vitest-environment node
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { OpenCodeClient, type OpenCodeEvent } from "@ai4s/sdk";
import { startMockOpenCode, type MockOpenCode } from "@ai4s/sdk/mock-server";

let server: MockOpenCode;

beforeAll(async () => {
  server = await startMockOpenCode(0);
});
afterAll(async () => {
  await server.close();
});

async function waitFor(pred: () => boolean, timeout = 3000) {
  const start = Date.now();
  while (!pred()) {
    if (Date.now() - start > timeout) throw new Error("timeout");
    await new Promise((r) => setTimeout(r, 10));
  }
}

describe("OpenCodeClient ↔ OpenCode server", () => {
  it("connects, creates a session, sends a prompt, and streams normalized events", async () => {
    const events: OpenCodeEvent[] = [];
    const client = new OpenCodeClient({ baseUrl: `http://127.0.0.1:${server.port}` });
    client.onEvent((e) => events.push(e));

    await client.connect();
    expect(client.getStatus()).toBe("ready");

    const sessionId = await client.createSession();
    expect(sessionId).toBe("ses_mock");

    await client.sendPrompt(sessionId, "run a literature review");
    await waitFor(() => events.some((e) => e.type === "session.idle"));

    const types = events.map((e) => e.type);
    expect(types).toContain("text.updated");
    expect(types).toContain("reasoning.updated");
    expect(types).toContain("step.updated");
    expect(types).toContain("tool.updated");
    expect(events).toContainEqual({
      type: "message.user",
      sessionId,
      messageID: "u1",
    });
    expect(events).toContainEqual({
      type: "message.usage",
      sessionId,
      messageId: "a1",
      parentMessageId: "u1",
      providerId: "mock-provider",
      modelId: "mock-model",
      agent: "build",
      systemContextContract: "ai4heor.system-context/v1",
      systemContextSha256: "b".repeat(64),
      systemContextBlockCount: 2,
      createdAt: 1,
      completedAt: 2,
      runtimeReportedCost: 0.0123,
      tokens: {
        input: 120,
        output: 45,
        reasoning: 8,
        cacheRead: 30,
        cacheWrite: 4,
      },
      finish: "stop",
    });
    expect(events.filter((event) => event.type === "message.usage")).toHaveLength(1);

    const reasoning = events
      .filter((e): e is Extract<OpenCodeEvent, { type: "reasoning.updated" }> =>
        e.type === "reasoning.updated" && e.partId === "r1",
      )
      .map((e) => e.text);
    expect(reasoning).toContain("Checking the evidence. ");
    expect(
      events.filter((e): e is Extract<OpenCodeEvent, { type: "step.updated" }> =>
        e.type === "step.updated",
      ).map((e) => e.step),
    ).toEqual([1, 2]);

    // Text streams live: each message.part.delta yields the accumulated text,
    // it does not sit silent until the full part arrives at text-end.
    const p1 = events
      .filter((e): e is Extract<OpenCodeEvent, { type: "text.updated" }> =>
        e.type === "text.updated" && e.partId === "p1",
      )
      .map((e) => e.text);
    expect(p1).toContain("Planning ");
    expect(p1[p1.length - 1]).toBe("Planning the analysis. ");

    const toolDone = events.find(
      (e): e is Extract<OpenCodeEvent, { type: "tool.updated" }> =>
        e.type === "tool.updated" && e.status === "success",
    );
    expect(toolDone?.title).toContain("literature-search");
    expect(toolDone?.messageId).toBe("a1");

    client.close();
    expect(client.getStatus()).toBe("offline");
  });

  it("lists slash commands (config commands + skills, one merged list)", async () => {
    const client = new OpenCodeClient({ baseUrl: `http://127.0.0.1:${server.port}` });
    const commands = await client.listCommands();
    expect(commands.map((c) => c.name)).toEqual(["init", "analyze-data"]);
    expect(commands[1].source).toBe("skill");
  });

  it("runs a shell command: bash tool part + session.idle stream back", async () => {
    const events: OpenCodeEvent[] = [];
    const client = new OpenCodeClient({ baseUrl: `http://127.0.0.1:${server.port}` });
    client.onEvent((e) => events.push(e));
    await client.connect();
    await client.runShell("ses_mock", "pwd");
    await waitFor(() => events.some((e) => e.type === "session.idle"));
    const bash = events.find(
      (e): e is Extract<OpenCodeEvent, { type: "tool.updated" }> =>
        e.type === "tool.updated" && e.tool === "bash",
    );
    expect(bash?.status).toBe("success");
    expect(bash?.output).toContain("/ws/mock");
    expect(bash?.messageId).toBe("ash1");
    client.close();
  });

  it("runs a slash command: a normal agent turn streams back", async () => {
    const events: OpenCodeEvent[] = [];
    const client = new OpenCodeClient({ baseUrl: `http://127.0.0.1:${server.port}` });
    client.onEvent((e) => events.push(e));
    await client.connect();
    await client.runCommand("ses_mock", "init", "focus on tests");
    await waitFor(() => events.some((e) => e.type === "session.idle"));
    expect(events.map((e) => e.type)).toContain("text.updated");
    client.close();
  });

  it("maps time.completed onto history messages and aborts a session", async () => {
    const client = new OpenCodeClient({ baseUrl: `http://127.0.0.1:${server.port}` });
    await client.connect();
    const sessionId = await client.createSession();
    await client.sendPrompt(sessionId, "run a literature review");
    const messages = await client.getMessages(sessionId);
    expect(messages[0].id).toBe("u1");
    const last = messages[messages.length - 1];
    expect(last.role).toBe("assistant");
    expect(last.completed).toBe(2); // the turn is over — the reconcile signal
    expect(last.usage).toEqual({
      sessionId,
      messageId: "a1",
      parentMessageId: "u1",
      providerId: "mock-provider",
      modelId: "mock-model",
      agent: "build",
      systemContextContract: "ai4heor.system-context/v1",
      systemContextSha256: "b".repeat(64),
      systemContextBlockCount: 2,
      createdAt: 1,
      completedAt: 2,
      runtimeReportedCost: 0.0123,
      tokens: {
        input: 120,
        output: 45,
        reasoning: 8,
        cacheRead: 30,
        cacheWrite: 4,
      },
      finish: "stop",
    });
    await expect(client.abortSession(sessionId)).resolves.toBeUndefined();
    client.close();
  });

  it("reverts and unreverts a task through the runtime endpoints", async () => {
    const client = new OpenCodeClient({ baseUrl: `http://127.0.0.1:${server.port}` });
    server.requests.length = 0;
    await client.revert("ses_mock", "u1");
    await client.unrevert("ses_mock");
    expect(server.requests).toEqual([
      "POST /session/ses_mock/revert",
      "POST /session/ses_mock/unrevert",
    ]);
  });

  it("reports an error status when the server is unreachable", async () => {
    const client = new OpenCodeClient({ baseUrl: "http://127.0.0.1:1" });
    await expect(client.connect()).rejects.toBeTruthy();
    expect(client.getStatus()).toBe("error");
  });

  it("disposes the cached instance after credential changes, so providers refresh", async () => {
    // The server caches its provider list per instance; PUT/DELETE /auth alone
    // leaves it stale (the new provider never appears in the UI). Verified on
    // opencode 1.17.13: POST /instance/dispose makes the change visible.
    const client = new OpenCodeClient({ baseUrl: `http://127.0.0.1:${server.port}` });

    server.requests.length = 0;
    await client.setProviderApiKey("mock", "sk-123");
    expect(server.requests).toEqual(["PUT /auth/mock", "POST /instance/dispose"]);

    server.requests.length = 0;
    await client.removeProviderAuth("mock");
    expect(server.requests).toEqual(["DELETE /auth/mock", "POST /instance/dispose"]);

    server.requests.length = 0;
    await client.oauthCallback("mock", 0);
    expect(server.requests).toEqual([
      "POST /provider/mock/oauth/callback",
      "POST /instance/dispose",
    ]);
  });

  it("disposes the workspace instance too when scoped to a directory", async () => {
    // Sessions run on the per-directory instance — if only the default one
    // were disposed, chats would keep a stale provider list until restart.
    const client = new OpenCodeClient({
      baseUrl: `http://127.0.0.1:${server.port}`,
      directory: "/ws/dir",
    });
    server.requests.length = 0;
    await client.setProviderApiKey("mock", "sk-123");
    expect(server.requests).toEqual([
      "PUT /auth/mock",
      "POST /instance/dispose",
      "POST /instance/dispose?directory=%2Fws%2Fdir",
    ]);
  });

  it("cancels a pending browser-login wait via the AbortSignal", async () => {
    // "auto" OAuth callbacks wait for the browser redirect — cancelling in
    // the UI must abort the request, not leak it on the sidecar.
    const client = new OpenCodeClient({ baseUrl: `http://127.0.0.1:${server.port}` });
    server.requests.length = 0;
    const abort = new AbortController();
    const pending = client.oauthCallback("slow", 0, undefined, abort.signal);
    await waitFor(() => server.requests.includes("POST /provider/slow/oauth/callback"));
    abort.abort();
    await expect(pending).rejects.toThrow();
    // An aborted login must not dispose the instance (nothing changed).
    expect(server.requests.filter((r) => r.includes("dispose"))).toEqual([]);
  });

  it("surfaces the server's diagnostic message when saving a key fails", async () => {
    const client = new OpenCodeClient({ baseUrl: `http://127.0.0.1:${server.port}` });
    await expect(client.setProviderApiKey("bad", "nope")).rejects.toThrow(/invalid key format/);
  });

  it("keeps custom-provider credentials out of the global config payload", async () => {
    const bodies: string[] = [];
    const fetchImpl: typeof fetch = async (_input, init) => {
      bodies.push(String(init?.body ?? ""));
      return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
    };
    const client = new OpenCodeClient({ baseUrl: "http://127.0.0.1:1", fetchImpl });

    await client.addCustomProvider("minimax-cn-token-plan", {
      name: "MiniMax CN Token Plan",
      npm: "@ai-sdk/anthropic",
      baseURL: "https://api.minimaxi.com/anthropic/v1",
      models: ["MiniMax-M3"],
    });

    const payload = JSON.parse(bodies[0]) as {
      provider: Record<string, { options: Record<string, unknown> }>;
    };
    expect(payload.provider["minimax-cn-token-plan"].options).toEqual({
      baseURL: "https://api.minimaxi.com/anthropic/v1",
    });
    expect(bodies[0]).not.toContain("apiKey");
  });

  it("pins a turn to the selected provider/model without exposing it in the text", async () => {
    const bodies: string[] = [];
    const fetchImpl: typeof fetch = async (_input, init) => {
      bodies.push(String(init?.body ?? ""));
      return new Response("{}", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };
    const client = new OpenCodeClient({ baseUrl: "http://127.0.0.1:1", fetchImpl });

    await client.sendPrompt(
      "ses_existing",
      "continue the HEOR analysis",
      undefined,
      "minimax-cn-token-plan/MiniMax-M3",
    );

    expect(JSON.parse(bodies[0])).toEqual({
      parts: [{ type: "text", text: "continue the HEOR analysis" }],
      model: {
        providerID: "minimax-cn-token-plan",
        modelID: "MiniMax-M3",
      },
    });
  });

  it("sends Basic auth on API calls when a password is set", async () => {
    // The sidecar now REQUIRES auth (OPENCODE_SERVER_PASSWORD) — every fetch
    // must carry the Authorization header or the server answers 401.
    const seen: (string | undefined)[] = [];
    const capturing: typeof fetch = (input, init) => {
      seen.push((init?.headers as Record<string, string> | undefined)?.["Authorization"]);
      return fetch(input, init);
    };
    const client = new OpenCodeClient({
      baseUrl: `http://127.0.0.1:${server.port}`,
      password: "pw-secret",
      fetchImpl: capturing,
    });
    await client.createSession();
    expect(seen[0]).toBe("Basic " + Buffer.from("opencode:pw-secret").toString("base64"));
  });

  it("keeps the EventSource stream when a password is set, authenticating via auth_token", async () => {
    // EventSource cannot set headers, but it is the reliable SSE path in the
    // WKWebView — the server accepts the same Basic payload as ?auth_token=.
    const urls: string[] = [];
    class FakeEventSource {
      onopen: (() => void) | null = null;
      onmessage: unknown = null;
      onerror: unknown = null;
      constructor(url: string) {
        urls.push(url);
        setTimeout(() => this.onopen?.(), 0);
      }
      close() {}
    }
    (globalThis as { EventSource?: unknown }).EventSource = FakeEventSource;
    try {
      const client = new OpenCodeClient({
        baseUrl: `http://127.0.0.1:${server.port}`,
        password: "pw-secret",
        directory: "/ws/dir",
      });
      await client.connect();
      expect(client.getStatus()).toBe("ready");
      const token = Buffer.from("opencode:pw-secret").toString("base64");
      expect(urls[0]).toContain(`auth_token=${encodeURIComponent(token)}`);
      expect(urls[0]).toContain(`directory=${encodeURIComponent("/ws/dir")}`);
      client.close();
    } finally {
      delete (globalThis as { EventSource?: unknown }).EventSource;
    }
  });

  it("times out a hanging EventSource handshake so boot retry can continue", async () => {
    class HangingEventSource {
      onopen: (() => void) | null = null;
      onmessage: unknown = null;
      onerror: unknown = null;
      close = vi.fn();
      constructor(_url: string) {}
    }
    (globalThis as { EventSource?: unknown }).EventSource = HangingEventSource;
    try {
      const client = new OpenCodeClient({
        baseUrl: `http://127.0.0.1:${server.port}`,
        connectTimeoutMs: 10,
      });
      await expect(client.connect()).rejects.toThrow("Timed out opening OpenCode event stream");
      expect(client.getStatus()).toBe("error");
    } finally {
      delete (globalThis as { EventSource?: unknown }).EventSource;
    }
  });

  it("times out a hanging session creation request", async () => {
    const hangingFetch = ((_input, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      })) as typeof fetch;
    const client = new OpenCodeClient({
      baseUrl: `http://127.0.0.1:${server.port}`,
      fetchImpl: hangingFetch,
      requestTimeoutMs: 10,
    });
    await expect(client.createSession()).rejects.toThrow("Timed out waiting for OpenCode");
  });

  it("times out a hanging history request", async () => {
    const hangingFetch = ((_input, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      })) as typeof fetch;
    const client = new OpenCodeClient({
      baseUrl: `http://127.0.0.1:${server.port}`,
      fetchImpl: hangingFetch,
      requestTimeoutMs: 10,
    });
    await expect(client.getMessages("ses_hung")).rejects.toThrow("Timed out waiting for OpenCode");
  });
});
