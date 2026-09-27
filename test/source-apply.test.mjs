import test from "node:test";
import assert from "node:assert/strict";

import {
  canApproveSourceReview,
  getSourceReviewActions,
  hasPersistedSourceBaseline,
  isSafeSourcePath,
  validateApplicableFiles,
} from "../src/source-apply.mjs";

test("source paths stay inside the selected folder", () => {
  for (const path of ["src/main.mjs", "docs/guide.md"]) assert.equal(isSafeSourcePath(path), true);
  for (const path of ["", "/etc/passwd", "../outside", "src/../outside", "src\\main.mjs", "src//main.mjs"]) {
    assert.equal(isSafeSourcePath(path), false, `${path} should be rejected`);
  }
});

test("applicable files must be unique and belong to the reviewed manifest", () => {
  const reviewed = [{ path: "src/main.mjs", content: "before" }];
  assert.deepEqual(
    validateApplicableFiles(reviewed, [{ path: "src/main.mjs", content: "after" }]),
    [{ path: "src/main.mjs", content: "after" }],
  );
  assert.throws(() => validateApplicableFiles(reviewed, [{ path: "README.md", content: "changed" }]), /unreviewed file/);
  assert.throws(() => validateApplicableFiles(reviewed, [
    { path: "src/main.mjs", content: "one" },
    { path: "src/main.mjs", content: "two" },
  ]), /duplicate file paths/);
  assert.throws(() => validateApplicableFiles(reviewed, [{ path: "../outside", content: "changed" }]), /invalid file/);
});

test("saved proposals stay viewable and can be approved with a persisted source baseline", () => {
  const restoredReview = {
    status: "PATCH_READY",
    relevantPaths: ["src/main.mjs"],
    sourceDigests: { "src/main.mjs": "abc123" },
  };
  const canApproveRestoredReview = hasPersistedSourceBaseline(restoredReview);
  assert.equal(canApproveRestoredReview, true);
  assert.equal(canApproveSourceReview(0, restoredReview), true);
  assert.deepEqual(getSourceReviewActions("PATCH_READY", false, canApproveRestoredReview), {
    showFix: false,
    showApprove: true,
    showSavedReview: true,
  });
  assert.deepEqual(getSourceReviewActions("PATCH_READY", false, hasPersistedSourceBaseline({ status: "PATCH_READY" })), {
    showFix: false,
    showApprove: false,
    showSavedReview: true,
  });
  assert.deepEqual(getSourceReviewActions("NOT_REQUESTED", true, false), {
    showFix: true,
    showApprove: false,
    showSavedReview: true,
  });
});

test("saved source baseline requires a digest for each relevant path", () => {
  const invalidBaseline = {
    relevantPaths: ["src/a.js", "src/b.js"],
    sourceDigests: { "src/a.js": "abc" },
  };
  assert.equal(hasPersistedSourceBaseline(invalidBaseline), false);
  assert.equal(canApproveSourceReview(0, invalidBaseline), false);
  assert.equal(hasPersistedSourceBaseline({ relevantPaths: [], sourceDigests: {} }), false);
});
