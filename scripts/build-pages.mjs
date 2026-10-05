import { cp, copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const output = resolve(process.argv[2] ?? resolve(root, "dist/pages"));
await mkdir(resolve(output, "src"), { recursive: true });
for (const file of await readdir(resolve(root, "src"))) {
  if (/\.(?:css|mjs)$/.test(file)) await copyFile(resolve(root, "src", file), resolve(output, "src", file));
}
await cp(resolve(root, "assets"), resolve(output, "assets"), { recursive: true });
await copyFile(resolve(root, "LICENSE"), resolve(output, "LICENSE"));
let html = await readFile(resolve(root, "index.html"), "utf8");
if (!html.includes('<html lang="en">') || !html.includes('<main id="main-content" class="page-shell">')) {
  throw new Error("The app entry changed; update the Pages walkthrough build.");
}
html = html.replace('<html lang="en">', '<html lang="en" data-demo="true">')
  .replace('</head>', '<link rel="stylesheet" href="./src/demo.css" />\n  </head>')
  .replace('Run a local keyboard assessment and review the evidence.', 'Explore AccessTrace with clearly labeled illustrative keyboard assessment results.')
  .replace('<title>AccessTrace — Keyboard assessment</title>', '<title>AccessTrace — Interactive demo</title>')
  .replace('<main id="main-content" class="page-shell">', `<main id="main-content" class="page-shell">
      <aside class="demo-banner" aria-label="Demo notice">
        <p><strong>Interactive demo · illustrative results.</strong> No website is assessed, and no data is sent to Codex.</p>
        <p>Play the example, explore its evidence, and review a proposed patch. For live assessments and applying fixes, <a href="https://github.com/terry-xyz/access-trace#run-accesstrace">run AccessTrace locally</a>.</p>
      </aside>`);
await writeFile(resolve(output, "index.html"), html);
await writeFile(resolve(output, ".nojekyll"), "");
console.log(`Pages walkthrough built at ${output}`);
