import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { buildSiteComparison } from "../src/comparison.mjs";
import { calculateWebsiteScore } from "../src/assessment.mjs";
import {
  AGENT_UPDATED_GOAL_FOCUSED_SAMPLE,
  AGENT_UPDATED_WHOLE_SITE_SAMPLE,
  GOAL_FOCUSED_SAMPLE,
  WHOLE_SITE_SAMPLE,
} from "../src/sample-report.mjs";

const pageMarkup = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const mainSource = readFileSync(new URL("../src/main.mjs", import.meta.url), "utf8");

const sharedSettings = {
  targetUrl: WHOLE_SITE_SAMPLE.target,
  scope: "whole-site",
  goal: null,
  simulationMode: true,
  interactionProfile: "Keyboard only",
  browserConditions: "Same controlled local browser conditions",
  consistencyLevel: "Low",
  runsPerVersion: 1,
};

function withSettings(sample, settings = sharedSettings) {
  return { ...sample, assessmentSettings: settings };
}

/** lowConsistencyComparisonExplainsBothScoresAndKeepsConflictingMetricsVisible. */
function lowConsistencyComparisonExplainsBothScoresAndKeepsConflictingMetricsVisible() {
  const original = withSettings(WHOLE_SITE_SAMPLE);
  const updated = withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE);
  const comparison = buildSiteComparison(original, updated);

  assert.equal(comparison.settings.consistencyLevel, "Low");
  assert.equal(comparison.settings.runsPerVersion, 1);
  assert.deepEqual(comparison.original, original);
  assert.deepEqual(comparison.updated, updated);
  assert.equal(comparison.outcome.status, "mixed");
  assert.match(comparison.outcome.summary, /Products link.*no matching updated observation/i);
  assert.equal(comparison.score.original.percentage, 82);
  assert.equal(comparison.score.updated.percentage, 95);
  assert.equal(comparison.score.deltaPercentagePoints, 13);
  assert.equal(comparison.coverage.original.checked, 7);
  assert.equal(comparison.coverage.updated.checked, 7);

  const focusMetric = comparison.metrics.find((metric) => metric.name === "Visible focus");
  const labelMetric = comparison.metrics.find((metric) => metric.name === "Form labels and instructions");
  assert.equal(focusMetric.passedDelta, 1);
  assert.equal(focusMetric.direction, "improved");
  assert.equal(labelMetric.passedDelta, -1);
  assert.equal(labelMetric.direction, "regressed");

  const productsFocusChange = comparison.evidence.focusChanges.find((change) => change.target === "Products");
  assert.equal(productsFocusChange.direction, "improved");
  assert.ok(comparison.evidence.additionalUpdatedFailures.some((action) => action.target === "Message field"));
}
test("a low-consistency comparison shows the higher score without hiding a metric regression", lowConsistencyComparisonExplainsBothScoresAndKeepsConflictingMetricsVisible);

/** evidenceWithoutRegressionsCanSupportAnImprovedOutcome. */
function evidenceWithoutRegressionsCanSupportAnImprovedOutcome() {
  const passingActions = WHOLE_SITE_SAMPLE.orderedActions.map((action) => ({ ...action, outcome: "passed" }));
  const passingFocus = WHOLE_SITE_SAMPLE.focusObservations.map((observation) => ({ ...observation, outcome: "passed" }));
  const original = withSettings({
    ...WHOLE_SITE_SAMPLE,
    orderedActions: passingActions,
    focusObservations: passingFocus,
  });
  const metrics = WHOLE_SITE_SAMPLE.metrics.map((metric) => (
    metric.name === "Keyboard reachability" ? { ...metric, passed: 7 } : metric
  ));
  const updatedPassed = metrics.reduce((sum, metric) => sum + metric.passed, 0);
  const updatedAttempted = metrics.reduce((sum, metric) => sum + metric.attempted, 0);
  const updated = withSettings({
    ...WHOLE_SITE_SAMPLE,
    runId: "SAMPLE-WS-IMPROVED-TEST",
    metrics,
    passed: updatedPassed,
    attempted: updatedAttempted,
    score: calculateWebsiteScore(updatedPassed, updatedAttempted),
    orderedActions: passingActions,
    focusObservations: passingFocus,
  });

  assert.equal(buildSiteComparison(original, updated).outcome.status, "improved");
}
test("complete aligned evidence without regressions can support an improved result", evidenceWithoutRegressionsCanSupportAnImprovedOutcome);

/** persistentFailuresRemainVisibleAndPreventAnUnqualifiedImprovedOutcome. */
function persistentFailuresRemainVisibleAndPreventAnUnqualifiedImprovedOutcome() {
  const original = withSettings(WHOLE_SITE_SAMPLE);
  const metrics = WHOLE_SITE_SAMPLE.metrics.map((metric) => (
    metric.name === "Keyboard reachability" ? { ...metric, passed: 7 } : metric
  ));
  const updatedPassed = metrics.reduce((sum, metric) => sum + metric.passed, 0);
  const updatedAttempted = metrics.reduce((sum, metric) => sum + metric.attempted, 0);
  const updated = withSettings({
    ...WHOLE_SITE_SAMPLE,
    runId: "SAMPLE-WS-PERSISTENT-FAILURE-TEST",
    metrics,
    passed: updatedPassed,
    attempted: updatedAttempted,
    score: calculateWebsiteScore(updatedPassed, updatedAttempted),
  });
  const comparison = buildSiteComparison(original, updated);

  assert.ok(comparison.score.deltaPercentagePoints > 0);
  assert.equal(comparison.outcome.status, "mixed");
  const persistentFailure = comparison.evidence.persistentFailures.find(({ target }) => target === "Products link");
  assert.ok(persistentFailure);
  assert.equal(persistentFailure.original.id, "ACT-03");
  assert.equal(persistentFailure.updated.id, "ACT-03");
  assert.match(comparison.outcome.summary, /Products link.*failed in both reports/i);

  const unchanged = buildSiteComparison(original, withSettings(WHOLE_SITE_SAMPLE));
  assert.equal(unchanged.outcome.status, "unresolved");
  assert.match(unchanged.outcome.summary, /remain failed in both reports/i);
}
test("persistent failed evidence stays visible beside score gains", persistentFailuresRemainVisibleAndPreventAnUnqualifiedImprovedOutcome);

/** newUpdatedFailurePreventsNumericGainsFromMaskingContradictoryEvidence. */
function newUpdatedFailurePreventsNumericGainsFromMaskingContradictoryEvidence() {
  const original = withSettings(WHOLE_SITE_SAMPLE);
  const metrics = WHOLE_SITE_SAMPLE.metrics.map((metric) => {
    if (metric.name === "Keyboard reachability") return { ...metric, passed: 7 };
    if (metric.name === "Visible focus") return { ...metric, passed: 5 };
    if (metric.name === "Focus order") return { ...metric, passed: 4 };
    return metric;
  });
  const updatedPassed = metrics.reduce((sum, metric) => sum + metric.passed, 0);
  const updatedAttempted = metrics.reduce((sum, metric) => sum + metric.attempted, 0);
  const updated = withSettings({
    ...AGENT_UPDATED_WHOLE_SITE_SAMPLE,
    metrics,
    passed: updatedPassed,
    attempted: updatedAttempted,
    score: calculateWebsiteScore(updatedPassed, updatedAttempted),
  });
  const comparison = buildSiteComparison(original, updated);

  assert.ok(comparison.score.deltaPercentagePoints > 0);
  assert.equal(comparison.outcome.status, "mixed");
  assert.match(comparison.outcome.summary, /Message field/i);
  assert.ok(comparison.evidence.additionalUpdatedFailures.length > 0);
}
test("an updated evidence failure prevents numeric gains from masking a contradiction", newUpdatedFailurePreventsNumericGainsFromMaskingContradictoryEvidence);

/** goalComparisonPreservesTheConfiguredGoalOnBothVersionReports. */
function goalComparisonPreservesTheConfiguredGoalOnBothVersionReports() {
  const goal = "Submit the contact form using only the keyboard";
  const goalSettings = { ...sharedSettings, scope: "goal-focused", goal };
  const original = withSettings({ ...GOAL_FOCUSED_SAMPLE, goal }, goalSettings);
  const updated = withSettings({ ...AGENT_UPDATED_GOAL_FOCUSED_SAMPLE, goal }, goalSettings);
  const comparison = buildSiteComparison(original, updated);

  assert.equal(comparison.outcome.status, "mixed");
  assert.equal(comparison.original.assessmentSettings.goal, goal);
  assert.equal(comparison.updated.assessmentSettings.goal, goal);
  assert.equal(comparison.original.assessmentSettings.scope, comparison.updated.assessmentSettings.scope);
}
test("the goal-focused comparison carries the same configured goal into both reports", goalComparisonPreservesTheConfiguredGoalOnBothVersionReports);

/** comparisonRefusesToCallMismatchedSettingsAnImprovement. */
function comparisonRefusesToCallMismatchedSettingsAnImprovement() {
  const original = withSettings(WHOLE_SITE_SAMPLE);
  const updatedSettings = { ...sharedSettings, simulationMode: false };
  const updated = withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE, updatedSettings);
  const comparison = buildSiteComparison(original, updated);

  assert.equal(comparison.outcome.status, "unresolved");
  assert.ok(comparison.settingDifferences.includes("simulationMode"));
}
test("different assessment settings make the comparison unresolved and name the difference", comparisonRefusesToCallMismatchedSettingsAnImprovement);

/** comparisonKeepsIncompleteEvidenceInTheUnresolvedOutcome. */
function comparisonKeepsIncompleteEvidenceInTheUnresolvedOutcome() {
  const original = withSettings(WHOLE_SITE_SAMPLE);
  const updated = withSettings({ ...AGENT_UPDATED_WHOLE_SITE_SAMPLE, terminalStatus: "INCONCLUSIVE" });
  const comparison = buildSiteComparison(original, updated);

  assert.equal(comparison.outcome.status, "unresolved");
  assert.equal(comparison.updated.terminalStatus, "INCONCLUSIVE");
}
test("an inconclusive version stays present and prevents a resolved comparison verdict", comparisonKeepsIncompleteEvidenceInTheUnresolvedOutcome);

/** comparisonSamplesKeepEveryEvidenceReferenceResolvable. */
function comparisonSamplesKeepEveryEvidenceReferenceResolvable() {
  const samples = [
    WHOLE_SITE_SAMPLE,
    AGENT_UPDATED_WHOLE_SITE_SAMPLE,
    GOAL_FOCUSED_SAMPLE,
    AGENT_UPDATED_GOAL_FOCUSED_SAMPLE,
  ];

  for (const sample of samples) {
    const ids = new Set([
      ...sample.orderedActions,
      ...sample.focusObservations,
      ...sample.recoveryEvidence,
      sample.screenshot,
    ].map((record) => record.id));
    for (const reference of sample.evidenceReferences) {
      assert.ok(ids.has(reference.id), `${reference.id} should resolve in ${sample.runId}`);
    }
  }

  assert.equal(
    AGENT_UPDATED_GOAL_FOCUSED_SAMPLE.orderedActions.find((action) => action.id === "ACT-GFU-02").outcome,
    "failed",
  );
}
test("all comparison sample evidence references resolve to the evidence they cite", comparisonSamplesKeepEveryEvidenceReferenceResolvable);

/** setupCanOpenComparisonAndBothReportsKeepTheirEvidenceAvailable. */
function setupCanOpenComparisonAndBothReportsKeepTheirEvidenceAvailable() {
  assert.match(pageMarkup, /id="view-comparison"/);
  assert.match(pageMarkup, /id="sample-comparison"[^>]*hidden/);
  assert.match(pageMarkup, /id="comparison-heading"/);
  assert.match(pageMarkup, /id="comparison-metrics-body"/);
  assert.match(pageMarkup, /id="comparison-original-report"/);
  assert.match(pageMarkup, /id="comparison-updated-report"/);
  assert.match(pageMarkup, /aria-labelledby="comparison-heading"/);
  assert.match(pageMarkup, /<th scope="col">Direction<\/th>/);
  assert.match(pageMarkup, /id="comparison-settings"/);
  assert.match(pageMarkup, /id="comparison-evidence-changes"/);
  assert.match(pageMarkup, /Representative sample — not live assessment/);
  assert.match(mainSource, /buildSiteComparison\(/);
  assert.match(mainSource, /validateTargetUrl\(/);
  assert.match(mainSource, /validateAssessmentGoal\(/);
  assert.match(mainSource, /interactionProfile: "Keyboard only"/);
  assert.match(mainSource, /browserConditions: "Same controlled local browser conditions"/);
  assert.match(mainSource, /runsPerVersion: 1/);
  assert.match(mainSource, /evidence\.persistentFailures/);
}
test("setup flows into an explicitly labeled comparison with both underlying reports available", setupCanOpenComparisonAndBothReportsKeepTheirEvidenceAvailable);
