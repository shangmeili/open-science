#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPT_DIR, "../..");
const DEFAULT_CONFIG = path.join(ROOT, "apps/desktop/src-tauri/tauri.conf.json");
const CACHE_DIRECTORIES = new Set([
  "__pycache__",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
]);
const GENERATED_FILES = new Set([".DS_Store", "Thumbs.db"]);

function parseArguments(argv) {
  if (argv.length === 0) return DEFAULT_CONFIG;
  if (argv.length === 2 && argv[0] === "--config") return path.resolve(argv[1]);
  throw new Error("usage: preflight_resources.mjs [--config TAURI_CONFIG]");
}

function generatedReason(target) {
  const name = path.basename(target);
  if (CACHE_DIRECTORIES.has(name)) return `generated cache directory: ${target}`;
  if (GENERATED_FILES.has(name)) return `generated operating-system file: ${target}`;
  if ([".pyc", ".pyo"].includes(path.extname(name).toLowerCase())) {
    return `generated Python cache file: ${target}`;
  }
  return null;
}

function inspectTree(source, sourceLabel, destination, files, problems) {
  const normalizedDestination = destination.replaceAll("\\", "/");
  const pending = [{ target: source, relative: "" }];
  while (pending.length > 0) {
    const { target, relative } = pending.pop();
    const reason = generatedReason(target);
    if (reason) {
      problems.push(reason);
      continue;
    }
    const stat = fs.lstatSync(target);
    if (stat.isSymbolicLink()) {
      problems.push(`resource contains a symbolic link: ${target}`);
      continue;
    }
    if (stat.isDirectory()) {
      const children = fs.readdirSync(target).sort().reverse();
      for (const child of children) {
        pending.push({
          target: path.join(target, child),
          relative: relative ? path.posix.join(relative, child) : child,
        });
      }
      continue;
    }
    if (!stat.isFile()) {
      problems.push(`resource is not a regular file or directory: ${target}`);
      continue;
    }
    const packagedPath = relative
      ? path.posix.join(normalizedDestination.replace(/\/+$/, ""), relative)
      : normalizedDestination;
    const prior = files.get(packagedPath);
    if (prior) {
      problems.push(
        `resource destination collision at ${packagedPath}: ${prior} and ${sourceLabel}`,
      );
      continue;
    }
    files.set(packagedPath, sourceLabel);
  }
}

function main() {
  const configPath = parseArguments(process.argv.slice(2));
  if (!fs.existsSync(configPath)) throw new Error(`Tauri config does not exist: ${configPath}`);
  const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  const resources = config?.bundle?.resources;
  if (!resources || Array.isArray(resources) || typeof resources !== "object") {
    throw new Error("bundle.resources must be a source-to-destination object");
  }

  const configRoot = path.dirname(configPath);
  const files = new Map();
  const problems = [];
  const entries = Object.entries(resources).sort(([left], [right]) => left.localeCompare(right));
  for (const [sourceLabel, destination] of entries) {
    if (typeof destination !== "string" || destination.trim() === "") {
      problems.push(`resource destination is invalid for ${sourceLabel}`);
      continue;
    }
    const source = path.resolve(configRoot, sourceLabel);
    if (!fs.existsSync(source)) {
      problems.push(`configured resource does not exist: ${source}`);
      continue;
    }
    inspectTree(source, sourceLabel, destination, files, problems);
  }

  if (problems.length > 0) {
    problems.sort();
    throw new Error(`release resource preflight failed:\n- ${problems.join("\n- ")}`);
  }
  process.stdout.write(
    `Release resource preflight passed: sources=${entries.length}, files=${files.size}\n`,
  );
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
