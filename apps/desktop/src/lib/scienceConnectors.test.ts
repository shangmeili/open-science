import { describe, expect, it } from "vitest";
import { SCIENCE_CONNECTORS, connectorConfig } from "./scienceConnectors";

function byId(id: string) {
  const connector = SCIENCE_CONNECTORS.find((item) => item.id === id);
  if (!connector) throw new Error(`missing connector ${id}`);
  return connector;
}

function localConfig(id: string, python: string, apiKey?: string) {
  const config = connectorConfig(byId(id), python, apiKey);
  if (config.type !== "local") throw new Error(`connector ${id} did not produce a local config`);
  return config;
}

describe("Open Science connector catalog", () => {
  it("retains the seven curated foundational connectors", () => {
    expect(SCIENCE_CONNECTORS.map((item) => item.id)).toEqual([
      "paper-search",
      "biomcp",
      "materials-project",
      "fred",
      "spaceweather",
      "open-meteo",
      "usgs-water",
    ]);
  });

  it("builds module, executable, Windows, and secret-bearing configs", () => {
    expect(localConfig("paper-search", "/env/bin/python").command).toEqual([
      "/env/bin/python",
      "-m",
      "paper_search_mcp.server",
    ]);
    expect(localConfig("materials-project", "/env/bin/python").command).toEqual([
      "/env/bin/mcp-materials-project",
    ]);
    expect(localConfig("fred", "C:\\env\\Scripts\\python.exe", " KEY ")).toEqual({
      type: "local",
      command: ["C:\\env\\Scripts\\fred-mcp.exe"],
      enabled: true,
      environment: { FRED_API_KEY: "KEY" },
    });
  });

  it("keeps source provenance and does not write blank credentials", () => {
    for (const connector of SCIENCE_CONNECTORS) {
      expect(connector.source).toMatch(/^github\.com\//);
      expect(connector.pkg).toMatch(/^[A-Za-z0-9._-]+$/);
    }
    expect(localConfig("fred", "/env/bin/python", "   ").environment).toBeUndefined();
  });
});
