import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const main = readFileSync(resolve(root, "src/main.tsx"), "utf8");
const app = readFileSync(resolve(root, "src/App.tsx"), "utf8");
const nova = readFileSync(resolve(root, "src/NovaPresentation.tsx"), "utf8");
const audio = readFileSync(resolve(root, "src/novaAudio.ts"), "utf8");
const styles = readFileSync(resolve(root, "src/nova.css"), "utf8");

const sceneIds = ["opening", "problem", "discovery", "analysis", "proposal", "control", "live", "closing"];
const audioFiles = sceneIds.map((id, index) =>
  resolve(root, `public/presentation/nova-${String(index + 1).padStart(2, "0")}-${id}.mp3`)
);

const checks = [
  ["nova video route does not steal /nova", main.includes('=== "/nova-video"') && main.includes("<NovaPresentation />")],
  ["nova live route", main.includes('=== "/nova"') && main.includes("<WebsiteProspectAgent />")],
  ["login nova film card", app.includes('href="/nova-video"') && app.includes("Nova · film")],
  ["film closes into nova live", nova.includes('href="/nova"') && nova.includes("Öppna Nova")],
  ["audio engine present", audio.includes("NovaAudioEngine")],
  ["film styles", styles.includes(".presentation--nova")],
  ...audioFiles.map((file, index) => [`audio file ${sceneIds[index]}`, readFileSync(file).byteLength > 1000])
];

for (const [label, passed] of checks) {
  if (!passed) {
    console.error(`Nova video check failed: ${label}`);
    process.exit(1);
  }
}

console.log("Nova video checks passed");
