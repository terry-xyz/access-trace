import test from "node:test";
import assert from "node:assert/strict";

import {
  CONTROLLED_TARGET_URL,
  calculateWebsiteScore,
  getAssessmentScope,
  validateTargetUrl,
} from "../src/assessment.mjs";
import { WHOLE_SITE_SAMPLE } from "../src/sample-report.mjs";

test("the recognized local target is accepted", () => {
  assert.deepEqual(validateTargetUrl(CONTROLLED_TARGET_URL), {
    valid: true,
    normalizedUrl: CONTROLLED_TARGET_URL,
    message: "",
  });
});

test("empty, malformed, remote, off-loopback, and unrecognized targets are rejected", () => {
  const invalidTargets = [
    "",
    "not a URL",
    "https://127.0.0.1:4173/",
    "http://example.com/",
    "http://192.168.1.20:4173/",
    "http://127.0.0.1:4174/",
    "http://127.0.0.1:4173/other-site",
  ];

  for (const target of invalidTargets) {
    assert.equal(validateTargetUrl(target).valid, false, `expected ${target} to be rejected`);
  }
});

test("a blank or whitespace-only goal selects a whole-site assessment", () => {
  assert.equal(getAssessmentScope(""), "whole-site");
  assert.equal(getAssessmentScope("   "), "whole-site");
});

test("a supplied goal selects a goal-focused assessment", () => {
  assert.equal(getAssessmentScope("Check the account navigation"), "goal-focused");
});

test("the score is passed website checks divided by attempted website checks", () => {
  assert.deepEqual(calculateWebsiteScore(18, 22), {
    passed: 18,
    attempted: 22,
    percentage: 82,
    label: "18 of 22 website checks passed",
  });
});

test("a report with no attempted website checks has no percentage score", () => {
  assert.deepEqual(calculateWebsiteScore(0, 0), {
    passed: 0,
    attempted: 0,
    percentage: null,
    label: "No website checks attempted",
  });
});

test("invalid check counts cannot produce a misleading score", () => {
  assert.throws(() => calculateWebsiteScore(-1, 4), RangeError);
  assert.throws(() => calculateWebsiteScore(5, 4), RangeError);
  assert.throws(() => calculateWebsiteScore(1.5, 4), RangeError);
});

test("the representative whole-site score matches the total of its named metrics", () => {
  const totals = WHOLE_SITE_SAMPLE.metrics.reduce(
    (sum, metric) => ({
      passed: sum.passed + metric.passed,
      attempted: sum.attempted + metric.attempted,
    }),
    { passed: 0, attempted: 0 },
  );

  assert.deepEqual(
    calculateWebsiteScore(totals.passed, totals.attempted),
    WHOLE_SITE_SAMPLE.score,
  );
});
