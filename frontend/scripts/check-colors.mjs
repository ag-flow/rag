// Contrôle automatisé de l'enabler « Fondations CSS » (75058a6a) :
// aucune couleur hexadécimale en dur dans les écrans — les couleurs vivent
// dans src/styles/tokens.css et se consomment via Tailwind ou var(--…).
// Usage : node scripts/check-colors.mjs (branché sur `npm run lint`).

import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const SRC = join(ROOT, "src");

// Exceptions justifiées — chaque entrée DOIT avoir un commentaire.
const EXCEPTIONS = new Set([
  "src/styles/tokens.css", // la source de vérité elle-même
]);

const HEX_RE = /#[0-9a-fA-F]{3,8}\b/g;
const EXTENSIONS = [".ts", ".tsx", ".css"];

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(path);
    else if (EXTENSIONS.some((ext) => entry.name.endsWith(ext))) yield path;
  }
}

const violations = [];
for (const path of walk(SRC)) {
  const rel = relative(ROOT, path);
  if (EXCEPTIONS.has(rel)) continue;
  const lines = readFileSync(path, "utf-8").split("\n");
  lines.forEach((line, i) => {
    const matches = line.match(HEX_RE);
    if (matches) violations.push(`${rel}:${i + 1}  ${matches.join(" ")}`);
  });
}

if (violations.length > 0) {
  console.error("Couleurs hexadécimales en dur détectées (utiliser les tokens) :");
  for (const v of violations) console.error(`  ${v}`);
  process.exit(1);
}
console.log("check-colors: aucun hexadécimal en dur hors tokens.css ✔");
