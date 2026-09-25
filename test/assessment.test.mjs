import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  CONTROLLED_TARGET_URL,
  calculateWebsiteScore,
  getAssessmentScope,
  validateTargetUrl,
} from "../src/assessment.mjs";
import { WHOLE_SITE_SAMPLE } from "../src/sample-report.mjs";

const reportMarkup = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const mainSource = readFileSync(new URL("../src/main.mjs", import.meta.url), "utf8");
const reportContent = reportMarkup.slice(
  reportMarkup.indexOf('<section id="sample-report"'),
  reportMarkup.indexOf("<footer"),
);

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

/** reportLeadPresentsScopeBeforeScore guards the outcome-first report reading order. */
function reportLeadPresentsScopeBeforeScore() {
  const leadSlots = ["terminal-status-value", "report-scope-lead", "score-percent", "metrics-grid"];
  const positions = [];

  for (const slot of leadSlots) {
    const position = reportMarkup.indexOf(`id="${slot}"`);
    assert.notEqual(position, -1, `${slot} must be present in the report`);
    positions.push(position);
  }

  for (let index = 1; index < positions.length; index += 1) {
    assert.ok(positions[index - 1] < positions[index], `${leadSlots[index]} must follow ${leadSlots[index - 1]}`);
  }
}
test("the report lead shows terminal result, scope, score, then named metrics", reportLeadPresentsScopeBeforeScore);

/** sampleReportFactsUseDataSlots keeps representative output owned by the sample record. */
function sampleReportFactsUseDataSlots() {
  const factSlots = [
    "terminalStatus",
    "scopeLabel",
    "outcomeTitle",
    "coverage",
    "explanationTitle",
    "explanation",
    "confidence",
    "confidenceContext",
    "proposedFixTitle",
    "proposedFix",
    "duration",
    "interactionCount",
    "goalSummary",
    "agentFailureSummary",
  ];

  for (const fact of factSlots) {
    assert.ok(reportMarkup.includes(`data-sample-fact="${fact}"`), `${fact} must render from the sample record`);
  }
  assert.ok(reportMarkup.includes('data-sample-link="wcagReference"'));
  assert.ok(reportMarkup.includes('data-sample-list="warnings"'));
  assert.ok(mainSource.includes('[data-sample-link="wcagReference"]'));
  assert.ok(mainSource.includes('[data-sample-list="warnings"]'));
  assert.ok(reportMarkup.includes('data-sample-fact="screenshotTitle"'));
  assert.ok(reportMarkup.includes('data-sample-fact="screenshotDescription"'));

  const duplicatedValues = [
    CONTROLLED_TARGET_URL,
    WHOLE_SITE_SAMPLE.runId,
    WHOLE_SITE_SAMPLE.terminalStatus,
    WHOLE_SITE_SAMPLE.outcomeTitle,
    WHOLE_SITE_SAMPLE.coverage,
    WHOLE_SITE_SAMPLE.duration,
    WHOLE_SITE_SAMPLE.explanationTitle,
    WHOLE_SITE_SAMPLE.explanation,
    WHOLE_SITE_SAMPLE.confidence,
    WHOLE_SITE_SAMPLE.confidenceContext,
    WHOLE_SITE_SAMPLE.proposedFixTitle,
    WHOLE_SITE_SAMPLE.proposedFix,
    WHOLE_SITE_SAMPLE.wcagReference.label,
    WHOLE_SITE_SAMPLE.wcagReference.url,
    WHOLE_SITE_SAMPLE.score.label,
    ...WHOLE_SITE_SAMPLE.metrics.map((metric) => metric.name),
    ...WHOLE_SITE_SAMPLE.orderedActions.flatMap((action) => [action.id, action.key, action.target, action.result]),
    ...WHOLE_SITE_SAMPLE.focusObservations.flatMap((observation) => [
      observation.id,
      observation.target,
      observation.role,
      observation.indicator,
    ]),
    ...WHOLE_SITE_SAMPLE.evidenceReferences.flatMap((reference) => [reference.id, reference.label]),
    WHOLE_SITE_SAMPLE.screenshot.id,
    WHOLE_SITE_SAMPLE.screenshot.title,
    WHOLE_SITE_SAMPLE.screenshot.siteName,
    ...WHOLE_SITE_SAMPLE.screenshot.navigation.map((item) => item.label),
    WHOLE_SITE_SAMPLE.screenshot.description,
    ...WHOLE_SITE_SAMPLE.recoveryEvidence.flatMap((evidence) => [evidence.id, evidence.text]),
    ...WHOLE_SITE_SAMPLE.warnings,
  ];
  for (const value of duplicatedValues) {
    const markup = value === CONTROLLED_TARGET_URL ? reportMarkup : reportContent;
    assert.ok(!markup.includes(value), `index.html must not hardcode sample value: ${value}`);
  }
}
test("representative facts render from the sample record instead of duplicated markup", sampleReportFactsUseDataSlots);
