#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPT_DIR, "../..");
const DEFAULT_CONFIG = path.join(ROOT, "apps/desktop/src-tauri/tauri.conf.json");

function parseArguments(argv) {
  if (argv.length === 0) return DEFAULT_CONFIG;
  if (argv.length === 2 && argv[0] === "--config") return path.resolve(argv[1]);
  throw new Error("usage: trigger_resource_staging.mjs [--config TAURI_CONFIG]");
}

function main() {
  const configPath = parseArguments(process.argv.slice(2));
  if (!fs.existsSync(configPath)) {
    throw new Error(`Tauri config does not exist: ${configPath}`);
  }
  const trigger = path.join(path.dirname(configPath), "resource-staging.trigger");
  const metadata = fs.lstatSync(trigger);
  if (!metadata.isFile() || metadata.isSymbolicLink()) {
    throw new Error(`resource staging trigger is not a regular file: ${trigger}`);
  }
  const now = new Date();
  fs.utimesSync(trigger, now, now);
  process.stdout.write("Tauri resource staging rebuild requested\n");
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
