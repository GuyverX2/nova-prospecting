import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../src/main.tsx", import.meta.url), "utf8");
for (const forbidden of ["salesos", "password", "username", "/login"]) {
  if (source.toLowerCase().includes(forbidden)) throw new Error(`forbidden frontend coupling: ${forbidden}`);
}
if (!source.includes("NOVA_PLATFORM_TOKEN") || !source.includes("Authorization: `Bearer ${token.trim()}`")) {
  throw new Error("frontend must consume and forward a platform bearer token");
}
