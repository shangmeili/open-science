// Curated open-source science MCP connectors inherited from Open Science.
// Each connector is provisioned on demand into an app-managed uv environment;
// it never modifies the researcher's Python installation.
import type { McpConfig } from "@ai4s/sdk";

export interface ScienceConnector {
  id: string;
  label: string;
  discipline: string;
  description: string;
  pkg: string;
  bin?: string;
  module?: string;
  args?: string[];
  apiKeyEnv?: string;
  apiKeyUrl?: string;
  installNote?: string;
  source: string;
}

export const SCIENCE_CONNECTORS: ScienceConnector[] = [
  {
    id: "paper-search",
    label: "Literature search",
    discipline: "all fields",
    description: "arXiv · PubMed · Crossref · Semantic Scholar · bioRxiv/medRxiv — search and fetch papers",
    pkg: "paper-search-mcp",
    module: "paper_search_mcp.server",
    source: "github.com/openags/paper-search-mcp",
  },
  {
    id: "biomcp",
    label: "Biomedical databases",
    discipline: "biology",
    description: "PubMed articles, ClinicalTrials.gov, and genomic variants (MyVariant/ClinVar)",
    pkg: "biomcp-python",
    module: "biomcp",
    args: ["run"],
    source: "github.com/genomoncology/biomcp",
  },
  {
    id: "materials-project",
    label: "Materials Project",
    discipline: "materials",
    description: "Query material properties, crystal structures, and phase diagrams",
    pkg: "mcp-materials-project",
    bin: "mcp-materials-project",
    apiKeyEnv: "MP_API_KEY",
    apiKeyUrl: "https://next-gen.materialsproject.org/api",
    installNote: "large — installs pymatgen and mp-api on first enable",
    source: "github.com/luffysolution-svg/mcp-materials-project",
  },
  {
    id: "fred",
    label: "FRED economic data",
    discipline: "economics",
    description: "Federal Reserve economic time series, including GDP, inflation, unemployment, and rates",
    pkg: "fred-mcp",
    bin: "fred-mcp",
    apiKeyEnv: "FRED_API_KEY",
    apiKeyUrl: "https://fred.stlouisfed.org/docs/api/api_key.html",
    source: "github.com/tosin2013/fred-mcp",
  },
  {
    id: "spaceweather",
    label: "Space weather",
    discipline: "physics",
    description: "Solar wind, flares, geomagnetic indices, radiation storms, and aurora forecasts",
    pkg: "spaceweather-mcp",
    bin: "spaceweather-mcp",
    source: "github.com/hoon1983/spaceweather-mcp",
  },
  {
    id: "open-meteo",
    label: "Weather and climate (Open-Meteo)",
    discipline: "earth/climate",
    description: "Current and historical weather, air quality, and timezone data",
    pkg: "mcp-weather-server",
    module: "mcp_weather_server",
    source: "github.com/isdaniel/mcp_weather_server",
  },
  {
    id: "usgs-water",
    label: "USGS water data",
    discipline: "earth/climate",
    description: "Streamflow, flood stages, peak events, and monitoring sites",
    pkg: "usgs-mcp",
    bin: "usgs-mcp",
    source: "github.com/mansurjisan/ocean-mcp",
  },
];

function scriptBeside(python: string, bin: string): string {
  const sep = python.includes("\\") ? "\\" : "/";
  const dir = python.slice(0, python.lastIndexOf(sep));
  const exe = python.toLowerCase().endsWith(".exe") ? ".exe" : "";
  return `${dir}${sep}${bin}${exe}`;
}

export function connectorConfig(
  connector: ScienceConnector,
  python: string,
  apiKey?: string,
): McpConfig {
  const command = connector.bin
    ? [scriptBeside(python, connector.bin)]
    : [python, "-m", connector.module ?? "", ...(connector.args ?? [])];
  const config: McpConfig = { type: "local", command, enabled: true };
  if (connector.apiKeyEnv && apiKey?.trim()) {
    config.environment = { [connector.apiKeyEnv]: apiKey.trim() };
  }
  return config;
}
