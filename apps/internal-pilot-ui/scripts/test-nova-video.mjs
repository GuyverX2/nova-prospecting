import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const main = readFileSync(resolve(root, "src/main.tsx"), "utf8");
const app = readFileSync(resolve(root, "src/App.tsx"), "utf8");
const nova = readFileSync(resolve(root, "src/NovaPresentation.tsx"), "utf8");
const audio = readFileSync(resolve(root, "src/novaAudio.ts"), "utf8");
const styles = readFileSync(resolve(root, "src/nova.css"), "utf8");
const loginStyles = readFileSync(resolve(root, "src/styles.css"), "utf8");

const checks = [
  ["nova video route does not steal /nova", main.includes('=== "/nova-video"') && main.includes("<NovaPresentation />")],
  ["arena nova demo kept", main.includes('=== "/nova"') && main.includes("<WebsiteProspectAgent demoOnly />")],
  ["login nova film card", app.includes('href="/nova-video"') && app.includes("Nova · film")],
  ["statusdemo remains", app.includes("/video/salesos-statusdemo-2026-08.mp4")],
  ["film closes into arena demo", nova.includes('href="/nova"') && nova.includes("Öppna Nova-demon")],
  ["human control wording", nova.includes("AI hjälper. Människan beslutar.")],
  ["no commercial readiness claim", !nova.includes("produktionsklar")],
  ["in-browser score", audio.includes("JINGLE_NOTES") && nova.includes("NovaAudioEngine")],
  ["captions", nova.includes("presentationCaption")],
  ["reduced motion", styles.includes("prefers-reduced-motion")],
  ["login nova card style", loginStyles.includes(".sessionNovaLink")]
];

for (const [label, passed] of checks) {
  if (!passed) {
    console.error(`Nova video check failed: ${label}`);
    process.exit(1);
  }
}

console.log("Nova video checks passed");
