import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  CONSISTENCY_RUN_COUNTS,
  buildSiteComparison,
} from "../src/comparison.mjs";
import { calculateWebsiteScore } from "../src/assessment.mjs";
import {
  AGENT_UPDATED_GOAL_FOCUSED_SAMPLE,
  AGENT_UPDATED_WHOLE_SITE_SAMPLE,
  GOAL_FOCUSED_SAMPLE,
  WHOLE_SITE_SAMPLE,
} from "../src/sample-report.mjs";

const pageMarkup = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const mainSource = readFileSync(new URL("../src/main.mjs", import.meta.url), "utf8");
const styleSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

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

/** reportWithMetrics makes an independent sample run whose score still matches its named checks. */
function reportWithMetrics(sample, settings, metrics, overrides = {}) {
  const totals = metrics.reduce(
    (result, metric) => ({
      passed: result.passed + metric.passed,
      attempted: result.attempted + metric.attempted,
    }),
    { passed: 0, attempted: 0 },
  );
  return withSettings({
    ...sample,
    ...overrides,
    metrics,
    ...totals,
    score: calculateWebsiteScore(totals.passed, totals.attempted),
  }, settings);
}

/** repeatedComparisonAveragesRunsAndRetainsEveryRunEvenWhenOneIsInconclusive. */
function repeatedComparisonAveragesRunsAndRetainsEveryRunEvenWhenOneIsInconclusive() {
  const settings = { ...sharedSettings, consistencyLevel: "Medium", runsPerVersion: 2 };
  const originalRunTwo = reportWithMetrics(WHOLE_SITE_SAMPLE, settings, [
    { name: "Keyboard reachability", passed: 6, attempted: 8 },
    { name: "Visible focus", passed: 5, attempted: 5 },
    { name: "Form labels and instructions", passed: 5, attempted: 5 },
    { name: "Focus order", passed: 3, attempted: 4 },
  ], { runId: "SAMPLE-WS-02", terminalStatus: "INCONCLUSIVE" });
  const updatedRunTwo = reportWithMetrics(AGENT_UPDATED_WHOLE_SITE_SAMPLE, settings, [
    { name: "Keyboard reachability", passed: 7, attempted: 8 },
    { name: "Visible focus", passed: 5, attempted: 5 },
    { name: "Form labels and instructions", passed: 3, attempted: 5 },
    { name: "Focus order", passed: 4, attempted: 4 },
  ], { runId: "SAMPLE-WS-UP-02", agentFailures: ["The sample planner retry was required."] });
  const originalRunOne = withSettings(WHOLE_SITE_SAMPLE, settings);
  const updatedRunOne = withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE, settings);
  const comparison = buildSiteComparison(
    [originalRunOne, originalRunTwo],
    [updatedRunOne, updatedRunTwo],
  );

  assert.equal(comparison.settings.consistencyLevel, "Medium");
  assert.equal(comparison.settings.runsPerVersion, 2);
  assert.equal(comparison.runs.original.length, 2);
  assert.equal(comparison.runs.updated.length, 2);
  assert.equal(comparison.runSummaries.original[1].terminalStatus, "INCONCLUSIVE");
  assert.deepEqual(comparison.runSummaries.updated[1].agentFailures, ["The sample planner retry was required."]);
  assert.equal(comparison.runs.original[1], originalRunTwo);
  assert.equal(comparison.evidenceByRun.length, 2);
  assert.ok(comparison.evidenceByRun[1].evidence.supportingChanges.length > 0);
  assert.equal(comparison.score.original.averagePercentage, 84);
  assert.deepEqual(comparison.score.original.range, { minimum: 82, maximum: 86 });
  assert.equal(comparison.score.original.scoredRuns, 2);
  assert.equal(comparison.score.updated.averagePercentage, 90.5);
  assert.deepEqual(comparison.score.updated.range, { minimum: 86, maximum: 95 });
  assert.equal(comparison.score.deltaPercentagePoints, 6.5);
  assert.equal(comparison.coverage.original.checked, 7);
  assert.equal(comparison.coverage.updated.checked, 7);
  assert.equal(comparison.coverage.comparable, true);
  assert.equal(comparison.outcome.label, "Mixed result");
  assert.match(comparison.outcome.summary, /Visible focus|improv/i);
  assert.match(comparison.outcome.summary, /Form labels and instructions|regress/i);
  assert.equal(comparison.metrics.find(({ name }) => name === "Form labels and instructions").direction, "regressed");
}
test("a repeated comparison averages scores and keeps inconclusive and agent-failed runs visible", repeatedComparisonAveragesRunsAndRetainsEveryRunEvenWhenOneIsInconclusive);

/** highConsistencyKeepsAnUnscoredRunVisibleAndUsesThreeRunsForBothVersions. */
function highConsistencyKeepsAnUnscoredRunVisibleAndUsesThreeRunsForBothVersions() {
  const settings = { ...sharedSettings, consistencyLevel: "High", runsPerVersion: 3 };
  const emptyMetrics = WHOLE_SITE_SAMPLE.metrics.map((metric) => ({
    name: metric.name,
    passed: 0,
    attempted: 0,
  }));
  const unscoredOriginal = reportWithMetrics(WHOLE_SITE_SAMPLE, settings, emptyMetrics, {
    runId: "SAMPLE-WS-03",
    terminalStatus: "INCONCLUSIVE",
  });
  const originalRuns = [
    withSettings(WHOLE_SITE_SAMPLE, settings),
    withSettings({ ...WHOLE_SITE_SAMPLE, runId: "SAMPLE-WS-02" }, settings),
    unscoredOriginal,
  ];
  const updatedRuns = [
    withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE, settings),
    withSettings({ ...AGENT_UPDATED_WHOLE_SITE_SAMPLE, runId: "SAMPLE-WS-UP-02" }, settings),
    withSettings({ ...AGENT_UPDATED_WHOLE_SITE_SAMPLE, runId: "SAMPLE-WS-UP-03" }, settings),
  ];
  const comparison = buildSiteComparison(originalRuns, updatedRuns);

  assert.equal(comparison.runs.original.length, 3);
  assert.equal(comparison.runs.updated.length, 3);
  assert.equal(comparison.settings.runsPerVersion, 3);
  assert.equal(comparison.score.original.scoredRuns, 2);
  assert.equal(comparison.score.original.unscoredRuns, 1);
  assert.equal(comparison.runSummaries.original[2].score.percentage, null);
  assert.match(comparison.outcome.summary, /original run 3 has no score/i);
}
test("High consistency retains all three runs and identifies an unscored run", highConsistencyKeepsAnUnscoredRunVisibleAndUsesThreeRunsForBothVersions);

/** incompleteRepeatedMetricsCannotProduceAnImprovedVerdict. */
function incompleteRepeatedMetricsCannotProduceAnImprovedVerdict() {
  const settings = { ...sharedSettings, consistencyLevel: "Medium", runsPerVersion: 2 };
  const incompleteMetrics = WHOLE_SITE_SAMPLE.metrics.map((metric) => (
    metric.name === "Visible focus"
      ? { ...metric, passed: 0, attempted: 0 }
      : metric
  ));
  const incompleteOriginal = reportWithMetrics(WHOLE_SITE_SAMPLE, settings, incompleteMetrics, {
    runId: "SAMPLE-WS-02",
  });
  const comparison = buildSiteComparison(
    [withSettings(WHOLE_SITE_SAMPLE, settings), incompleteOriginal],
    [
      withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE, settings),
      withSettings({ ...AGENT_UPDATED_WHOLE_SITE_SAMPLE, runId: "SAMPLE-WS-UP-02" }, settings),
    ],
  );

  assert.equal(
    comparison.metrics.find(({ name }) => name === "Visible focus").direction,
    "unavailable",
  );
  assert.notEqual(comparison.outcome.status, "improved");
  assert.match(comparison.outcome.summary, /insufficient repeated-run data/i);
}
test("incomplete repeated metrics cannot produce an Improved verdict", incompleteRepeatedMetricsCannotProduceAnImprovedVerdict);

/** comparisonSetupOffersAccessibleDataDrivenConsistencyLevels. */
function comparisonSetupOffersAccessibleDataDrivenConsistencyLevels() {
  assert.match(pageMarkup, /<label[^>]*for="comparison-consistency"/);
  assert.match(pageMarkup, /<select[^>]*id="comparison-consistency"[^>]*name="consistencyLevel"/);
  assert.deepEqual(CONSISTENCY_RUN_COUNTS, { Low: 1, Medium: 2, High: 3 });
  assert.match(mainSource, /function populateConsistencyOptions\(\)/);
  assert.match(mainSource, /const consistencyLevel = consistencyInput\.value/);
  assert.match(mainSource, /    consistencyLevel,/);
  assert.match(mainSource, /runsPerVersion: CONSISTENCY_RUN_COUNTS\[consistencyLevel\]/);
}
test("comparison setup exposes Low, Medium, and High consistency with Low selected by default", comparisonSetupOffersAccessibleDataDrivenConsistencyLevels);

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

  const productsFocusChange = comparison.evidence.assessmentChanges.find((change) => change.kind === "focus" && change.target === "Products");
  assert.equal(productsFocusChange.direction, "improved");
  assert.ok(comparison.evidence.additionalUpdatedFailures.some((action) => action.target === "Message field"));
}
test("a low-consistency comparison shows the higher score without hiding a metric regression", lowConsistencyComparisonExplainsBothScoresAndKeepsConflictingMetricsVisible);

/** comparisonSummarizesDifferencesAcrossRecoveryScreenshotAndCitations. */
function comparisonSummarizesDifferencesAcrossRecoveryScreenshotAndCitations() {
  const comparison = buildSiteComparison(
    withSettings(WHOLE_SITE_SAMPLE),
    withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE),
  );
  const supportingChanges = comparison.evidence.supportingChanges;

  for (const kind of ["recovery", "screenshot", "reference"]) {
    assert.ok(supportingChanges.some((change) => change.kind === kind), `${kind} differences should be modeled`);
  }
  const screenshotChange = supportingChanges.find((change) => change.kind === "screenshot");
  assert.equal(screenshotChange.change, "changed");
  assert.ok(screenshotChange.changedFields.includes("navigation"));
  assert.ok(supportingChanges.some((change) => change.kind === "recovery" && change.change === "added"));
  assert.ok(supportingChanges.some((change) => change.kind === "reference" && change.change === "removed"));
}
test("comparison models recovery, screenshot, and evidence-reference differences", comparisonSummarizesDifferencesAcrossRecoveryScreenshotAndCitations);

/** comparisonKeepsAddedAndRemovedPassingAssessmentRecordsVisible. */
function comparisonKeepsAddedAndRemovedPassingAssessmentRecordsVisible() {
  const comparison = buildSiteComparison(
    withSettings(WHOLE_SITE_SAMPLE),
    withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE),
  );

  assert.ok(comparison.evidence.assessmentChanges.some((change) => (
    change.kind === "action" && change.change === "added" && change.record.target === "Submit control"
  )));
  assert.ok(comparison.evidence.assessmentChanges.some((change) => (
    change.kind === "action" && change.change === "removed" && change.record.target === "Search field"
  )));
}
test("comparison summarizes added and removed passing action evidence", comparisonKeepsAddedAndRemovedPassingAssessmentRecordsVisible);

/** comparisonMetricTableCanBeReachedAndOperatedAtNarrowWidths. */
function comparisonMetricTableCanBeReachedAndOperatedAtNarrowWidths() {
  const metricsPanel = pageMarkup.match(/<section class="report-panel comparison-metrics-panel"[\s\S]*?<\/section>/)?.[0];

  assert.ok(metricsPanel);
  assert.match(metricsPanel, /<div class="table-scroll comparison-metrics-scroll"[^>]*role="region"[^>]*tabindex="0"/);
  assert.match(metricsPanel, /aria-labelledby="comparison-metrics-heading"/);
  assert.match(metricsPanel, /aria-describedby="comparison-metrics-scroll-help"/);
  assert.match(metricsPanel, /id="comparison-metrics-scroll-help"[^>]*>[^<]*scroll horizontally[^<]*/i);
  assert.equal([...metricsPanel.matchAll(/<th scope="col">/g)].length, 5);
  assert.match(styleSource, /\.table-scroll \{ overflow-x: auto;/);
  assert.match(styleSource, /\.comparison-metrics-scroll:focus-visible/);
}
test("the five-column metric table is keyboard-scrollable with an accessible cue", comparisonMetricTableCanBeReachedAndOperatedAtNarrowWidths);

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

  const mediumSettings = { ...sharedSettings, consistencyLevel: "Medium", runsPerVersion: 2 };
  const missingRepeat = buildSiteComparison(
    withSettings(WHOLE_SITE_SAMPLE, mediumSettings),
    withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE, mediumSettings),
  );
  assert.equal(missingRepeat.outcome.label, "Mixed result");
  assert.match(missingRepeat.outcome.summary, /expects 2 runs per version/i);
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
  assert.match(pageMarkup, /Meaningful differences across actions, recovery, screenshots, and evidence citations/);
  assert.match(pageMarkup, /Representative sample — not live assessment/);
  assert.match(mainSource, /buildSiteComparison\(/);
  assert.match(mainSource, /renderComparisonEvidence\(comparison\.evidenceByRun\)/);
  assert.match(mainSource, /validateTargetUrl\(/);
  assert.match(mainSource, /validateAssessmentGoal\(/);
  assert.match(mainSource, /interactionProfile: "Keyboard only"/);
  assert.match(mainSource, /browserConditions: "Same controlled local browser conditions"/);
  assert.match(mainSource, /runsPerVersion: CONSISTENCY_RUN_COUNTS\[consistencyLevel\]/);
  assert.match(mainSource, /renderComparisonReports\(/);
  assert.match(mainSource, /representativeRunNote/);
  assert.match(mainSource, /terminalStatus: "INCONCLUSIVE"/);
  assert.match(mainSource, /terminalStatus: "AGENT_FAILED"/);
  assert.match(mainSource, /Representative agent failure retained for this sample slot/);
  assert.match(mainSource, /formatReportScore\(sample\.score\)/);
  assert.match(mainSource, /container\.append\(fragment\)/);
  assert.match(mainSource, /function appendComparisonHeading\(parent, text\)[\s\S]*?createElement\("h5"\)/);
  assert.match(styleSource, /\.comparison-report-content h4, \.comparison-report-content h5/);
  assert.match(pageMarkup, /id="comparison-run-results"/);
  assert.match(pageMarkup, /id="comparison-original-range"/);
  assert.match(pageMarkup, /id="comparison-updated-range"/);
  assert.match(mainSource, /evidence\.persistentFailures/);
  assert.match(mainSource, /appendComparisonParagraph\(fragment, "Duration", sample\.duration\)/);
  assert.match(mainSource, /appendComparisonParagraph\(fragment, "Interaction count", String\(sample\.interactionCount\)\)/);
  assert.match(mainSource, /appendComparisonScreenshot\(/);
}
test("setup flows into an explicitly labeled comparison with both underlying reports available", setupCanOpenComparisonAndBothReportsKeepTheirEvidenceAvailable);
