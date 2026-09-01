import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const main = readFileSync(resolve(root, "src/main.tsx"), "utf8");
const app = readFileSync(resolve(root, "src/App.tsx"), "utf8");
const nova = readFileSync(resolve(root, "src/NovaPresentation.tsx"), "utf8");
const audio = readFileSync(resolve(root, "src/novaAudio.ts"), "utf8");
const styles = readFileSync(resolve(root, "src/nova.css"), "utf8");

/**
 * LOCALE-COVERAGE-AUDIT-001: hardcoded copy moved into the pilot-ext catalog, so
 * a view now renders `tr("pilot-ext.…")` instead of the literal. A needle still
 * has to hold either inline OR in the English value of a key the file renders.
 */
const catalog = readFileSync(resolve(root, "../shared/ui/locale/messages/pilot-ext.ts"), "utf8");
const catalogPairs = [...catalog.matchAll(/"(pilot-ext\.[^"]+)":\s*"((?:[^"\\]|\\.)*)"/g)].map((m) => [m[1], m[2]]);
function has(src, needle) {
  if (src.includes(needle)) return true;
  return catalogPairs.some(([key, value]) => value.includes(needle) && src.includes(`"${key}"`));
}

const sceneIds = ["opening", "problem", "discovery", "analysis", "proposal", "control", "live", "closing"];
const audioFiles = sceneIds.map((id, index) =>
  resolve(root, `public/presentation/nova-${String(index + 1).padStart(2, "0")}-${id}.mp3`)
);

const checks = [
  ["nova video route does not steal /nova", main.includes('=== "/nova-video"') && has(main, "<NovaPresentation />")],
  ["nova live route", main.includes('=== "/nova"') && has(main, "<WebsiteProspectAgent />")],
  ["login nova film card", app.includes('href="/nova-video"') && has(app, "Nova · film")],
  ["film closes into nova live", nova.includes('href="/nova"') && has(nova, "Öppna Nova")],
  ["audio engine present", has(audio, "NovaAudioEngine")],
  ["film styles", has(styles, ".presentation--nova")],
  ...audioFiles.map((file, index) => [`audio file ${sceneIds[index]}`, readFileSync(file).byteLength > 1000])
];

for (const [label, passed] of checks) {
  if (!passed) {
    console.error(`Nova video check failed: ${label}`);
    process.exit(1);
  }
}

console.log("Nova video checks passed");
