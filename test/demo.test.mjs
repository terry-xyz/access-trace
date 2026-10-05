import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { demoFetch, EXAMPLE_RUN } from "../src/demo.mjs";

test("the walkthrough replays labeled example data and rejects live operations", async () => {
  const body = JSON.stringify({ targetUrl: EXAMPLE_RUN.targetUrl, goal: null, pageOnly: true });
  assert.equal((await demoFetch("/api/runs", { method: "POST", body })).status, 201);
  const active = await (await demoFetch(`/api/runs/${EXAMPLE_RUN.id}`)).json();
  assert.equal(active.status, "IN_PROGRESS");
  const record = await (await demoFetch(`/api/runs/${EXAMPLE_RUN.id}/execute`, { method: "POST" })).json();
  assert.equal(record.status, "COMPLETED");
  assert.match(record.provenance, /Illustrative/);
  assert.equal(record.interactionCount, record.actions.length);
  assert.equal(record.stoppingPoint.coverage.scorePercentage, 75);
  assert.equal(record.sourceReview.status, "PATCH_READY");
  assert.equal(EXAMPLE_RUN.status, "COMPLETED");
  assert.equal((await demoFetch("/api/runs", { method: "POST", body: "not JSON" })).status, 400);
  assert.equal((await demoFetch("/api/runs", { method: "POST", body: body.replace("example.test", "other.test") })).status, 400);
  for (const path of ["/api/sites", `/api/runs/${EXAMPLE_RUN.id}/source-fix-approve`, "https://example.com/"]) {
    assert.equal((await demoFetch(path, { method: "POST" })).status, 501);
  }
});

test("the Pages build marks its demo and ships only static assets with relative paths", async (t) => {
  const prefix = join(tmpdir(), "access-trace-pages-");
  const output = await mkdtemp(prefix);
  assert.ok(output.startsWith(prefix));
  t.after(() => rm(output, { recursive: true, force: true }));
  execFileSync(process.execPath, ["scripts/build-pages.mjs", output]);
  const html = await readFile(join(output, "index.html"), "utf8");
  assert.match(html, /data-demo="true"/);
  assert.match(html, /illustrative results/);
  assert.match(html, /No website is assessed/);
  assert.match(html, /href="\.\/src\/demo.css"/);
  assert.match(html, /id="run-report-template"/);
  assert.deepEqual((await readdir(output)).sort(), [".nojekyll", "LICENSE", "assets", "index.html", "src"]);
  const main = await readFile(join(output, "src/main.mjs"), "utf8");
  assert.match(main, /const apiFetch = demo\?\.demoFetch \?\? fetch/);
  assert.doesNotMatch(main, /\bfetch\(/);
  assert.doesNotMatch(await readFile("index.html", "utf8"), /data-demo=/);
});
