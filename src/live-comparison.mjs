export const CONSISTENCY_RUN_COUNTS = Object.freeze({ Low: 1, Medium: 2, High: 3 });

/** summarizeLiveComparisonCounts groups only raw facts present on successful run records. */
export function summarizeLiveComparisonCounts(slots) {
  const terminalStatuses = new Map();
  const coverageGroups = new Map();
  const successOutcomes = {
    reached: 0,
    notReached: 0,
    notRecorded: 0,
    notConfigured: 0,
  };
  let missingTerminalStatus = 0;
  let missingCoverage = 0;
  let creationFailures = 0;
  let executionFailures = 0;
  let recordedRuns = 0;

  for (const slot of Array.isArray(slots) ? slots : []) {
    const record = slot && typeof slot === "object" ? slot.record : null;
    if (!record || typeof record !== "object") {
      if (slot?.failureStage === "creation") {
        creationFailures += 1;
      } else {
        executionFailures += 1;
      }
      continue;
    }
    recordedRuns += 1;

    const evidence = record.evidenceHandoff && typeof record.evidenceHandoff === "object"
      ? record.evidenceHandoff
      : {};
    const stats = evidence.stats && typeof evidence.stats === "object" ? evidence.stats : {};
    const status = nonEmptyString(stats.terminalStatus) || nonEmptyString(record.status);
    if (status) terminalStatuses.set(status, (terminalStatuses.get(status) || 0) + 1);
    else missingTerminalStatus += 1;

    const coverage = stats.coverage
      ?? evidence.stopping?.point?.coverage
      ?? evidence.progress?.coverage;
    const coverageStatus = nonEmptyString(coverage?.status);
    const unit = hasCount(coverage?.controlsObserved) || hasCount(coverage?.controlsExpected)
      ? "controls"
      : hasCount(coverage?.areasObserved) || hasCount(coverage?.areasExpected)
        ? "areas"
        : null;
    const observed = unit === "controls"
      ? firstCount(coverage, ["controlsObserved"])
      : unit === "areas" ? firstCount(coverage, ["areasObserved"]) : null;
    const expected = unit === "controls"
      ? firstCount(coverage, ["controlsExpected"])
      : unit === "areas" ? firstCount(coverage, ["areasExpected"]) : null;
    if (observed === null && expected === null && !coverageStatus) {
      missingCoverage += 1;
    } else {
      const key = JSON.stringify([observed, expected, coverageStatus, unit]);
      const group = coverageGroups.get(key) || {
        observed,
        expected,
        status: coverageStatus,
        unit,
        count: 0,
      };
      group.count += 1;
      coverageGroups.set(key, group);
    }

    const stopping = evidence.stopping?.point && typeof evidence.stopping.point === "object"
      ? evidence.stopping.point
      : {};
    const assessment = evidence.assessment && typeof evidence.assessment === "object"
      ? evidence.assessment
      : {};
    const successCondition = nonEmptyString(stopping.successCondition)
      || nonEmptyString(assessment.successCondition)
      || nonEmptyString(record.successCondition);
    if (!successCondition) {
      successOutcomes.notConfigured += 1;
    } else {
      const matched = typeof stopping.successMatched === "boolean"
        ? stopping.successMatched
        : typeof record.successMatched === "boolean" ? record.successMatched : null;
      if (matched === true) successOutcomes.reached += 1;
      else if (matched === false) successOutcomes.notReached += 1;
      else successOutcomes.notRecorded += 1;
    }
  }

  return {
    processedSlots: Array.isArray(slots) ? slots.length : 0,
    recordedRuns,
    creationFailures,
    executionFailures,
    terminalStatuses: [...terminalStatuses.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([status, count]) => ({ status, count })),
    missingTerminalStatus,
    coverageGroups: [...coverageGroups.values()],
    missingCoverage,
    successOutcomes,
  };
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function firstCount(value, fields) {
  if (!value || typeof value !== "object") return null;
  for (const field of fields) {
    if (Number.isFinite(value[field]) && value[field] >= 0) return value[field];
  }
  return null;
}

function hasCount(value) {
  return Number.isFinite(value) && value >= 0;
}
