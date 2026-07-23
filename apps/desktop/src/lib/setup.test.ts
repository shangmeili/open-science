// The setup store owns the long-running uv provisioning flows so they survive
// page navigation. These guard the two properties that broke before: a second
// concurrent start must not race the first into the same env dir, and the
// busy/generation lifecycle must be observable regardless of which page reads.
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  addMcpServer: vi.fn(async () => {}),
  loadCatalog: vi.fn(async () => {}),
  restartLocalRuntime: vi.fn(async () => true),
  /** Resolver for the in-flight setupJupyter promise, so tests hold it open. */
  resolveSetup: (() => {}) as () => void,
  setupJupyter: vi.fn(),
  startJupyter: vi.fn(async () => ({
    url: "http://127.0.0.1:9",
    token: "tok",
    mcp_command: "/env/bin/jupyter-mcp-server",
  })),
}));

mocks.setupJupyter.mockImplementation(
  () => new Promise<void>((r) => (mocks.resolveSetup = () => r())),
);

vi.mock("./runtime", () => ({
  getClient: () => ({ addMcpServer: mocks.addMcpServer }),
  useRuntimeStore: {
    getState: () => ({
      loadCatalog: mocks.loadCatalog,
      restartLocalRuntime: mocks.restartLocalRuntime,
    }),
  },
}));
vi.mock("./tauri", () => ({
  setupJupyter: mocks.setupJupyter,
  startJupyter: mocks.startJupyter,
  watchSetupProgress: async () => () => {},
}));
vi.mock("./toast", () => ({ toast: { success: () => {}, error: () => {} } }));

import { useSetupStore } from "./setup";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.setupJupyter.mockImplementation(
    () => new Promise<void>((r) => (mocks.resolveSetup = () => r())),
  );
  useSetupStore.setState({
    jupyterBusy: false,
    browserBusy: false,
    line: null,
    generation: 0,
  });
});

describe("setup store", () => {
  it("marks busy while provisioning Jupyter and clears + bumps generation after", async () => {
    const gen0 = useSetupStore.getState().generation;
    const run = useSetupStore.getState().enableJupyter();
    expect(useSetupStore.getState().jupyterBusy).toBe(true); // set synchronously

    mocks.resolveSetup();
    await run;

    const s = useSetupStore.getState();
    expect(s.jupyterBusy).toBe(false);
    expect(s.line).toBeNull();
    expect(s.generation).toBe(gen0 + 1);
    expect(mocks.addMcpServer).toHaveBeenCalledWith("jupyter", expect.anything());
    expect(mocks.restartLocalRuntime).toHaveBeenCalledTimes(1);
  });

  it("ignores a second concurrent enableJupyter — no colliding provisioning run", async () => {
    const p1 = useSetupStore.getState().enableJupyter();
    const p2 = useSetupStore.getState().enableJupyter(); // guarded: returns at once
    await p2; // the guarded call resolves without waiting on the first
    expect(mocks.setupJupyter).toHaveBeenCalledTimes(1);

    mocks.resolveSetup();
    await p1;
    expect(mocks.setupJupyter).toHaveBeenCalledTimes(1);
  });

  it("installs the managed Python environment without starting or registering Jupyter", async () => {
    const gen0 = useSetupStore.getState().generation;
    const run = useSetupStore.getState().installManagedPython();
    expect(useSetupStore.getState().jupyterBusy).toBe(true);

    mocks.resolveSetup();
    await run;

    expect(mocks.setupJupyter).toHaveBeenCalledTimes(1);
    expect(mocks.startJupyter).not.toHaveBeenCalled();
    expect(mocks.addMcpServer).not.toHaveBeenCalled();
    expect(useSetupStore.getState()).toMatchObject({
      jupyterBusy: false,
      line: null,
      generation: gen0 + 1,
    });
  });

  it("guards the managed Python installer against a second concurrent run", async () => {
    const p1 = useSetupStore.getState().installManagedPython();
    const p2 = useSetupStore.getState().installManagedPython();
    await p2;
    expect(mocks.setupJupyter).toHaveBeenCalledTimes(1);

    mocks.resolveSetup();
    await p1;
    expect(mocks.setupJupyter).toHaveBeenCalledTimes(1);
  });
});
