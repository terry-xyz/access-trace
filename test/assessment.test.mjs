import test from "node:test";
import assert from "node:assert/strict";

import {
  CONTROLLED_TARGET_URL,
  calculateWebsiteScore,
  getAssessmentScope,
  validateAssessmentGoal,
  validateTargetUrl,
} from "../src/assessment.mjs";

test("target validation accepts absolute HTTP and HTTPS URLs and normalizes them", () => {
  assert.deepEqual(validateTargetUrl(CONTROLLED_TARGET_URL), {
    valid: true,
    normalizedUrl: CONTROLLED_TARGET_URL,
    message: "",
  });
  assert.equal(validateTargetUrl(" https://example.test/path ").normalizedUrl,
    "https://example.test/path");
  assert.equal(validateTargetUrl("http://127.0.0.1:4173/other").valid, true);
});

test("target validation rejects empty, malformed, unsafe-scheme, and credential URLs", () => {
  for (const value of ["", "not a URL", "javascript:alert(1)", "file:///tmp/page.html", "https://user:pass@example.test/"]) {
    assert.equal(validateTargetUrl(value).valid, false, `expected rejection for ${value}`);
  }
});

test("blank goals select whole-site scope and nonblank goals are trimmed and retained", () => {
  assert.equal(getAssessmentScope("  \t "), "whole-site");
  assert.equal(getAssessmentScope("Review the account navigation"), "goal-focused");
  assert.deepEqual(validateAssessmentGoal("  Submit the contact form  "), {
    valid: true,
    scope: "goal-focused",
    goal: "Submit the contact form",
    reason: "",
    message: "",
  });
  assert.deepEqual(validateAssessmentGoal(" "), {
    valid: true,
    scope: "whole-site",
    goal: "",
    reason: "",
    message: "",
  });
});

test("goal length is bounded while other goal wording is passed through", () => {
  assert.equal(validateAssessmentGoal("Evaluate color contrast").valid, true);
  const tooLong = validateAssessmentGoal("x".repeat(501));
  assert.equal(tooLong.valid, false);
  assert.equal(tooLong.reason, "too-long");
});

test("website scores use passed over attempted checks and leave empty runs unscored", () => {
  assert.deepEqual(calculateWebsiteScore(18, 22), {
    passed: 18,
    attempted: 22,
    percentage: 82,
    label: "18 of 22 website checks passed",
  });
  assert.deepEqual(calculateWebsiteScore(0, 0), {
    passed: 0,
    attempted: 0,
    percentage: null,
    label: "No website checks attempted",
  });
});

test("invalid website-check counts cannot produce a score", () => {
  for (const [passed, attempted] of [[-1, 4], [5, 4], [1.5, 4], [0, NaN]]) {
    assert.throws(() => calculateWebsiteScore(passed, attempted), RangeError);
  }
});
