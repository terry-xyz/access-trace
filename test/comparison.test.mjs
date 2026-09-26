import test from "node:test";
import assert from "node:assert/strict";

import {
  CONSISTENCY_RUN_COUNTS,
  buildSiteComparison,
  formatCount,
  formatTerminalStatus,
} from "../src/comparison.mjs";
import { calculateWebsiteScore } from "../src/assessment.mjs";
import {
  AGENT_UPDATED_WHOLE_SITE_SAMPLE,
  WHOLE_SITE_SAMPLE,
} from "../src/sample-report.mjs";

const settings = {
  targetUrl: WHOLE_SITE_SAMPLE.target,
  scope: "whole-site",
  goal: null,
  simulationMode: true,
  interactionProfile: "Keyboard only",
  browserConditions: "Same controlled local browser conditions",
  consistencyLevel: "Low",
  runsPerVersion: 1,
};

function withSettings(report, overrides = {}) {
  return { ...report, assessmentSettings: { ...settings, ...overrides } };
}

test("terminal statuses and counts use stable readable labels", () => {
  assert.equal(formatTerminalStatus("AGENT_FAILED"), "Agent failed");
  assert.equal(formatTerminalStatus("INCONCLUSIVE"), "Inconclusive");
  assert.equal(formatTerminalStatus("unknown"), "Unknown");
  assert.equal(formatCount(1, "run"), "1 run");
  assert.equal(formatCount(2, "assessment"), "2 assessments");
  assert.equal(formatCount(undefined, "run"), "an unknown number of runs");
  assert.deepEqual(CONSISTENCY_RUN_COUNTS, { Low: 1, Medium: 2, High: 3 });
});

test("comparison retains both reports and summarizes score, metrics, and evidence changes", () => {
  const original = withSettings(WHOLE_SITE_SAMPLE);
  const updated = withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE);
  const comparison = buildSiteComparison(original, updated);

  assert.equal(comparison.original, original);
  assert.equal(comparison.updated, updated);
  assert.equal(comparison.runs.original[0], original);
  assert.equal(comparison.runs.updated[0], updated);
  assert.equal(comparison.score.original.percentage, 82);
  assert.equal(comparison.score.updated.percentage, 95);
  assert.ok(comparison.metrics.length > 0);
  assert.ok(comparison.evidence.assessmentChanges.length > 0);
  assert.ok(comparison.evidence.supportingChanges.some((change) => change.kind === "reference"));
});

test("repeated comparisons retain run records and aggregate scores", () => {
  const medium = { consistencyLevel: "Medium", runsPerVersion: 2 };
  const first = withSettings(WHOLE_SITE_SAMPLE, medium);
  const second = withSettings({ ...WHOLE_SITE_SAMPLE, runId: "WS-02" }, medium);
  const updatedFirst = withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE, medium);
  const updatedSecond = withSettings({ ...AGENT_UPDATED_WHOLE_SITE_SAMPLE, runId: "WS-UP-02" }, medium);
  const comparison = buildSiteComparison([first, second], [updatedFirst, updatedSecond]);

  assert.equal(comparison.runs.original.length, 2);
  assert.equal(comparison.runs.updated.length, 2);
  assert.equal(comparison.runSummaries.original.length, 2);
  assert.equal(comparison.score.original.averagePercentage, 82);
  assert.equal(comparison.score.updated.averagePercentage, 95);
});

test("mismatched run settings are reported and prevent a resolved verdict", () => {
  const original = withSettings(WHOLE_SITE_SAMPLE);
  const updated = withSettings(AGENT_UPDATED_WHOLE_SITE_SAMPLE, { simulationMode: false });
  const comparison = buildSiteComparison(original, updated);

  assert.ok(comparison.settingDifferences.includes("simulationMode"));
  assert.equal(comparison.outcome.status, "unresolved");
});

test("comparison preserves inconclusive reports as unresolved evidence", () => {
  const original = withSettings(WHOLE_SITE_SAMPLE);
  const updated = withSettings({ ...AGENT_UPDATED_WHOLE_SITE_SAMPLE, terminalStatus: "INCONCLUSIVE" });
  const comparison = buildSiteComparison(original, updated);

  assert.equal(comparison.updated.terminalStatus, "INCONCLUSIVE");
  assert.equal(comparison.outcome.status, "unresolved");
});

test("report evidence links resolve to records in the same report", () => {
  const ids = new Set([
    ...WHOLE_SITE_SAMPLE.orderedActions,
    ...WHOLE_SITE_SAMPLE.focusObservations,
    ...WHOLE_SITE_SAMPLE.recoveryEvidence,
    WHOLE_SITE_SAMPLE.screenshot,
  ].map((record) => record.id));
  for (const reference of WHOLE_SITE_SAMPLE.evidenceReferences) {
    assert.ok(ids.has(reference.id), `${reference.id} must identify a report record`);
  }
  assert.equal(calculateWebsiteScore(18, 22).percentage, 82);
});
