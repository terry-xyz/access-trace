import test from "node:test";
import assert from "node:assert/strict";

import {
  CONTROLLED_TARGET_URL,
  calculateWebsiteScore,
  getAssessmentScope,
  validateTargetUrl,
} from "../src/assessment.mjs";
import { WHOLE_SITE_SAMPLE } from "../src/sample-report.mjs";

/** recognizedTargetIsAccepted verifies the one canonical endpoint kept inside the local demo boundary. */
function recognizedTargetIsAccepted() {
  assert.deepEqual(validateTargetUrl(CONTROLLED_TARGET_URL), {
    valid: true,
    normalizedUrl: CONTROLLED_TARGET_URL,
    message: "",
  });
}
test("the recognized local target is accepted", recognizedTargetIsAccepted);

/** invalidTargetsAreRejected prevents loopback lookalikes and remote URLs from entering setup. */
function invalidTargetsAreRejected() {
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
}
test("empty, malformed, remote, off-loopback, and unrecognized targets are rejected", invalidTargetsAreRejected);

/** blankGoalSelectsWholeSite keeps whitespace from silently selecting goal-focused mode. */
function blankGoalSelectsWholeSite() {
  assert.equal(getAssessmentScope(""), "whole-site");
  assert.equal(getAssessmentScope("   "), "whole-site");
}
test("a blank or whitespace-only goal selects a whole-site assessment", blankGoalSelectsWholeSite);

/** suppliedGoalSelectsGoalFocused confirms scope follows the user's non-empty goal. */
function suppliedGoalSelectsGoalFocused() {
  assert.equal(getAssessmentScope("Check the account navigation"), "goal-focused");
}
test("a supplied goal selects a goal-focused assessment", suppliedGoalSelectsGoalFocused);

/** scoreUsesWebsiteCheckCounts compares the formula to a fixed worked example from the ticket. */
function scoreUsesWebsiteCheckCounts() {
  assert.deepEqual(calculateWebsiteScore(18, 22), {
    passed: 18,
    attempted: 22,
    percentage: 82,
    label: "18 of 22 website checks passed",
  });
}
test("the score is passed website checks divided by attempted website checks", scoreUsesWebsiteCheckCounts);

/** emptyScoreHasNoPercentage avoids implying a score when no website check ran. */
function emptyScoreHasNoPercentage() {
  assert.deepEqual(calculateWebsiteScore(0, 0), {
    passed: 0,
    attempted: 0,
    percentage: null,
    label: "No website checks attempted",
  });
}
test("a report with no attempted website checks has no percentage score", emptyScoreHasNoPercentage);

/** invalidCountsCannotProduceScore rejects impossible totals before they reach a report. */
function invalidCountsCannotProduceScore() {
  const invalidCounts = [
    calculateWebsiteScore.bind(null, -1, 4),
    calculateWebsiteScore.bind(null, 5, 4),
    calculateWebsiteScore.bind(null, 1.5, 4),
  ];
  for (const check of invalidCounts) assert.throws(check, RangeError);
}
test("invalid check counts cannot produce a misleading score", invalidCountsCannotProduceScore);

/** sampleScoreMatchesMetricTotals catches drift between the headline score and named metrics. */
function sampleScoreMatchesMetricTotals() {
  const totals = { passed: 0, attempted: 0 };
  for (const metric of WHOLE_SITE_SAMPLE.metrics) {
    totals.passed += metric.passed;
    totals.attempted += metric.attempted;
  }

  assert.deepEqual(
    calculateWebsiteScore(totals.passed, totals.attempted),
    WHOLE_SITE_SAMPLE.score,
  );
}
test("the representative whole-site score matches the total of its named metrics", sampleScoreMatchesMetricTotals);

/** evidenceReferencesResolve guards the sample's in-report links against orphaned citations. */
function evidenceReferencesResolve() {
  const evidenceIds = new Set();
  const evidenceRecords = [
    ...WHOLE_SITE_SAMPLE.orderedActions,
    ...WHOLE_SITE_SAMPLE.focusObservations,
    ...WHOLE_SITE_SAMPLE.recoveryEvidence,
    WHOLE_SITE_SAMPLE.screenshot,
  ];
  for (const record of evidenceRecords) evidenceIds.add(record.id);

  for (const reference of WHOLE_SITE_SAMPLE.evidenceReferences) {
    assert.ok(evidenceIds.has(reference.id), `${reference.id} should resolve to sample evidence`);
  }
}
test("every representative evidence reference points to its matching evidence record", evidenceReferencesResolve);
