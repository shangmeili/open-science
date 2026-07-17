/** Product-owned connector surface. External MCP servers remain user-managed
 *  until a hash-locked adapter passes the packaged admission registry. */
export const FIRST_PARTY_HEOR_CONNECTOR = {
  id: "heor-evidence-search",
  sources: ["PubMed", "ClinicalTrials.gov"],
  implementation: "native-fixed-endpoint",
  humanAuthorizationRequired: true,
  agentMayAuthorize: false,
} as const;

/** No third-party process is a one-click default in AI4HEOR. */
export const DEFAULT_EXTERNAL_MCP_CONNECTORS = [] as const;

/** Upgrade compatibility only: already-configured servers keep running and
 *  remain removable, but these generic Open Science entries are never offered
 *  to a new AI4HEOR installation. */
export const RETIRED_ONE_CLICK_CONNECTOR_IDS = [
  "paper-search",
  "biomcp",
  "materials-project",
  "fred",
  "spaceweather",
  "open-meteo",
  "usgs-water",
] as const;
