/**
 * Static guardrails for the Nova console.
 *
 * Nova must stay independently deployable: the frontend may not reference the
 * SalesOS platform, may not implement its own login, and must forward the
 * platform-issued bearer token. It also must not pin itself to an absolute API
 * host or persist the token, both of which have broken deployments before.
 */
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

const SRC = new URL("../src/", import.meta.url);

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(directory.pathname ?? directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await sourceFiles(path)));
    } else if (/\.(ts|tsx|css)$/.test(entry.name)) {
      files.push(path);
    }
  }
  return files;
}

const failures = [];
const files = await sourceFiles(SRC);
if (files.length === 0) {
  failures.push("no frontend sources found");
}

const sources = new Map();
for (const file of files) {
  sources.set(file, await readFile(file, "utf8"));
}

const FORBIDDEN = [
  ["salesos", "the console must not reference the SalesOS platform"],
  ["/login", "Nova has no login flow; the platform issues tokens"],
  ["localStorage", "the bearer token must not be persisted in the browser"],
  ["sessionStorage", "the bearer token must not be persisted in the browser"],
  ["dangerouslysetinnerhtml", "untrusted content must never be injected as HTML"],
  ["http://localhost", "the API host must not be hard-coded"],
  ["127.0.0.1", "the API host must not be hard-coded"],
];

for (const [file, source] of sources) {
  const lowered = source.toLowerCase();
  for (const [needle, reason] of FORBIDDEN) {
    if (lowered.includes(needle)) {
      failures.push(`${file}: ${reason} (found "${needle}")`);
    }
  }
  if (/\bany\b\s*[;,)=>]/.test(source) && file.endsWith(".ts")) {
    failures.push(`${file}: 'any' defeats the typed API contract`);
  }
}

const api = sources.get(join(SRC.pathname, "api.ts")) ?? "";
if (!api.includes("Authorization: `Bearer ${token.trim()}`")) {
  failures.push("api.ts must forward the platform bearer token");
}
if (!api.includes('"/api/v1"')) {
  failures.push("api.ts must default to the same-origin /api/v1 base path");
}

const app = sources.get(join(SRC.pathname, "App.tsx")) ?? "";
if (!app.includes("NOVA_PLATFORM_TOKEN")) {
  failures.push("App.tsx must accept a platform-issued token");
}
for (const flow of ["/prospecting/prospects", "analysis", "approve", "deliver"]) {
  if (!(app + api).toLowerCase().includes(flow.toLowerCase())) {
    failures.push(`the console must cover the ${flow} step of the operator flow`);
  }
}

if (failures.length > 0) {
  console.error("Static frontend checks failed:");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`Static frontend checks passed (${files.length} files).`);
