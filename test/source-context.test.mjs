import test from "node:test";
import assert from "node:assert/strict";

import { filterSensitiveFiles, isSensitiveSourcePath } from "../src/source-context.mjs";

test("obvious credential files and directories are excluded from source review", () => {
  for (const path of [
    ".env", "app/.env.production", "app/.env.local", "app/.envrc", ".npmrc", "src/.pypirc",
    "home/.netrc", ".ssh/id_rsa", "project/.aws/credentials", "app/.kube/config",
    "src/private.key", "certs/client.p12", "certs/client.pfx", "secrets/credentials.json",
    "config/service-account.json", "config/access-token.json",
  ]) {
    assert.equal(isSensitiveSourcePath(path), true, `${path} should be excluded`);
  }
});

test("ordinary source and configuration files remain eligible", () => {
  for (const path of [
    "src/main.mjs", "src/config.json", "docs/environment.md", "src/tokenizer.py",
    "src/keybindings.js", "tests/test_credentials.py", "README.md",
  ]) {
    assert.equal(isSensitiveSourcePath(path), false, `${path} should remain eligible`);
  }
});

test("page folder upload omits credential files without dropping page assets", () => {
  const entries = [
    { path: "index.html", file: { size: 120 } },
    { path: "assets/site.css", file: { size: 30 } },
    { path: ".env.local", file: { size: 20 } },
    { path: "keys/private.pem", file: { size: 200 } },
  ];
  const result = filterSensitiveFiles(entries);
  assert.deepEqual(result.entries.map(({ path }) => path), ["index.html", "assets/site.css"]);
  assert.equal(result.skippedCount, 2);
});
