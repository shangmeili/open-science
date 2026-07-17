import { describe, expect, it } from "vitest";
import {
  DEFAULT_EXTERNAL_MCP_CONNECTORS,
  FIRST_PARTY_HEOR_CONNECTOR,
  RETIRED_ONE_CLICK_CONNECTOR_IDS,
} from "./heorConnectorPolicy";

describe("AI4HEOR connector policy", () => {
  it("ships no unreviewed external MCP process as a one-click default", () => {
    expect(DEFAULT_EXTERNAL_MCP_CONNECTORS).toEqual([]);
  });

  it("keeps built-in evidence retrieval fixed, bounded, and Human-authorized", () => {
    expect(FIRST_PARTY_HEOR_CONNECTOR).toEqual({
      id: "heor-evidence-search",
      sources: ["PubMed", "ClinicalTrials.gov"],
      implementation: "native-fixed-endpoint",
      humanAuthorizationRequired: true,
      agentMayAuthorize: false,
    });
  });

  it("does not silently re-offer inherited Open Science connectors", () => {
    expect(RETIRED_ONE_CLICK_CONNECTOR_IDS).toEqual([
      "paper-search",
      "biomcp",
      "materials-project",
      "fred",
      "spaceweather",
      "open-meteo",
      "usgs-water",
    ]);
  });
});
