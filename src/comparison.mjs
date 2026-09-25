import { calculateWebsiteScore } from "./assessment.mjs";

const COMPARISON_SETTING_FIELDS = [
  "targetUrl",
  "scope",
  "goal",
  "simulationMode",
  "interactionProfile",
  "browserConditions",
  "consistencyLevel",
  "runsPerVersion",
];

/** buildSiteComparison compares report evidence only when both versions share the same settings. */
export function buildSiteComparison(original, updated) {
  const settingDifferences = findSettingDifferences(
    original.assessmentSettings,
    updated.assessmentSettings,
  );
  const metricNamesMatch = haveSameMetricNames(original.metrics, updated.metrics);
  const originalMetrics = Array.isArray(original.metrics) ? original.metrics : [];
  const updatedMetrics = Array.isArray(updated.metrics) ? updated.metrics : [];
  const metrics = compareMetrics(originalMetrics, updatedMetrics);
  const originalScore = getReportScore(original);
  const updatedScore = getReportScore(updated);
  const scoreDelta = getDelta(originalScore.percentage, updatedScore.percentage);
  const coverage = compareCoverage(original, updated);
  const everyMetricComparable = metrics.length > 0
    && metrics.every((metric) => metric.percentagePointDelta !== null);
  const integrityProblems = [
    ...settingDifferences.map((field) => `The versions use different ${field} settings.`),
    ...(!isLowConsistencyPair(original.assessmentSettings)
      ? ["This representative comparison requires one Low-consistency assessment per version."]
      : []),
    ...(!reportMatchesSettings(original)
      ? ["The original report does not match its declared assessment settings."]
      : []),
    ...(!reportMatchesSettings(updated)
      ? ["The updated report does not match its declared assessment settings."]
      : []),
    ...(original.terminalStatus !== "COMPLETED"
      ? [`The original assessment is ${original.terminalStatus.toLowerCase()}.`]
      : []),
    ...(updated.terminalStatus !== "COMPLETED"
      ? [`The updated assessment is ${updated.terminalStatus.toLowerCase()}.`]
      : []),
    ...(!metricNamesMatch ? ["The versions do not contain the same named metrics."] : []),
    ...(!everyMetricComparable ? ["At least one named metric has insufficient check data to compare."] : []),
    ...(!coverage.comparable ? ["Comparable coverage counts are unavailable."] : []),
    ...(!metricsAreInternallyConsistent(original)
      ? ["The original metric totals do not match its reported score counts."]
      : []),
    ...(!metricsAreInternallyConsistent(updated)
      ? ["The updated metric totals do not match its reported score counts."]
      : []),
    ...(!reportScoreMatchesCounts(original)
      ? ["The original score does not match its reported check counts."]
      : []),
    ...(!reportScoreMatchesCounts(updated)
      ? ["The updated score does not match its reported check counts."]
      : []),
    ...(originalScore.percentage === null || updatedScore.percentage === null
      ? ["At least one assessment has no score to compare."]
      : []),
  ];
  const outcome = chooseOutcome({
    integrityProblems,
    metrics,
    scoreDelta,
    coverage,
  });

  return {
    original,
    updated,
    settings: { ...original.assessmentSettings },
    settingDifferences,
    score: {
      original: originalScore,
      updated: updatedScore,
      deltaPercentagePoints: scoreDelta,
    },
    metrics,
    coverage,
    outcome,
  };
}

/** isLowConsistencyPair ensures one report per version is not mislabeled as a repeated comparison. */
function isLowConsistencyPair(settings = {}) {
  return settings.consistencyLevel === "Low" && settings.runsPerVersion === 1;
}

/** findSettingDifferences names any assessment setting that prevents a fair comparison. */
function findSettingDifferences(originalSettings = {}, updatedSettings = {}) {
  return COMPARISON_SETTING_FIELDS.filter((field) => (
    originalSettings[field] === undefined
    || updatedSettings[field] === undefined
    || originalSettings[field] !== updatedSettings[field]
  ));
}

/** haveSameMetricNames prevents a missing metric from looking like a zero or an improvement. */
function haveSameMetricNames(originalMetrics, updatedMetrics) {
  if (!Array.isArray(originalMetrics) || !Array.isArray(updatedMetrics)) return false;
  const originalNames = originalMetrics.map(({ name }) => name);
  const updatedNames = updatedMetrics.map(({ name }) => name);
  return originalNames.length === updatedNames.length
    && new Set(originalNames).size === originalNames.length
    && new Set(updatedNames).size === updatedNames.length
    && originalNames.every((name) => updatedNames.includes(name));
}

/** reportMatchesSettings catches a report paired with a settings snapshot for another target or goal. */
function reportMatchesSettings(report) {
  const settings = report.assessmentSettings;
  return settings
    && report.target === settings.targetUrl
    && report.scope === settings.scope
    && (report.goal ?? null) === settings.goal;
}

/** compareMetrics keeps every named measurement and its direction in the comparison result. */
function compareMetrics(originalMetrics, updatedMetrics) {
  const updatedByName = new Map(updatedMetrics.map((metric) => [metric.name, metric]));
  const originalNames = new Set(originalMetrics.map((metric) => metric.name));
  const rows = originalMetrics.map((originalMetric) => {
    const updatedMetric = updatedByName.get(originalMetric.name);
    return compareMetric(originalMetric, updatedMetric);
  });

  for (const updatedMetric of updatedMetrics) {
    if (!originalNames.has(updatedMetric.name)) rows.push(compareMetric(null, updatedMetric));
  }

  return rows;
}

/** compareMetric calculates both raw check-count changes and pass-rate changes. */
function compareMetric(original, updated) {
  const originalPercentage = getPassPercentage(original);
  const updatedPercentage = getPassPercentage(updated);
  const percentagePointDelta = getDelta(originalPercentage, updatedPercentage);

  return {
    name: original?.name ?? updated.name,
    original: original ? { ...original, percentage: originalPercentage } : null,
    updated: updated ? { ...updated, percentage: updatedPercentage } : null,
    passedDelta: original && updated ? updated.passed - original.passed : null,
    attemptedDelta: original && updated ? updated.attempted - original.attempted : null,
    percentagePointDelta,
    direction: percentagePointDelta === null
      ? "unavailable"
      : percentagePointDelta > 0
        ? "improved"
        : percentagePointDelta < 0
          ? "regressed"
          : "unchanged",
  };
}

/** getReportScore recomputes the familiar score formula from each report's check counts. */
function getReportScore(report) {
  try {
    const score = calculateWebsiteScore(report.passed, report.attempted);
    return {
      passed: score.passed,
      attempted: score.attempted,
      percentage: score.percentage,
    };
  } catch {
    return {
      passed: Number.isInteger(report.passed) ? report.passed : null,
      attempted: Number.isInteger(report.attempted) ? report.attempted : null,
      percentage: null,
    };
  }
}

/** reportScoreMatchesCounts prevents an independently stored score from contradicting its counts. */
function reportScoreMatchesCounts(report) {
  if (!report.score) return false;
  const calculated = getReportScore(report);
  return calculated.percentage !== null
    && report.score.passed === calculated.passed
    && report.score.attempted === calculated.attempted
    && report.score.percentage === calculated.percentage;
}

/** compareCoverage retains each version's coverage text and reports numeric changes when available. */
function compareCoverage(original, updated) {
  const originalStats = original.coverageStats;
  const updatedStats = updated.coverageStats;
  const comparable = isValidCoverage(originalStats) && isValidCoverage(updatedStats);
  const originalPercentage = comparable ? percentage(originalStats.checked, originalStats.total) : null;
  const updatedPercentage = comparable ? percentage(updatedStats.checked, updatedStats.total) : null;

  return {
    original: {
      label: original.coverage,
      checked: originalStats?.checked ?? null,
      total: originalStats?.total ?? null,
      percentage: originalPercentage,
    },
    updated: {
      label: updated.coverage,
      checked: updatedStats?.checked ?? null,
      total: updatedStats?.total ?? null,
      percentage: updatedPercentage,
    },
    checkedDelta: comparable ? updatedStats.checked - originalStats.checked : null,
    totalDelta: comparable ? updatedStats.total - originalStats.total : null,
    percentagePointDelta: getDelta(originalPercentage, updatedPercentage),
    comparable,
  };
}

/** isValidCoverage rejects impossible counts before they can support an improvement claim. */
function isValidCoverage(coverageStats) {
  return coverageStats
    && Number.isInteger(coverageStats.checked)
    && Number.isInteger(coverageStats.total)
    && coverageStats.total > 0
    && coverageStats.checked >= 0
    && coverageStats.checked <= coverageStats.total;
}

/** metricsAreInternallyConsistent prevents score and named metrics from contradicting each other. */
function metricsAreInternallyConsistent(report) {
  if (!Array.isArray(report.metrics)) return false;
  if (!report.metrics.every((metric) => (
    Number.isInteger(metric.passed)
    && Number.isInteger(metric.attempted)
    && metric.passed >= 0
    && metric.attempted >= metric.passed
  ))) return false;

  const totals = report.metrics.reduce(
    (sum, metric) => ({
      passed: sum.passed + metric.passed,
      attempted: sum.attempted + metric.attempted,
    }),
    { passed: 0, attempted: 0 },
  );
  return totals.passed === report.passed && totals.attempted === report.attempted;
}

/** chooseOutcome requires aligned settings and complete evidence before it calls a result improved. */
function chooseOutcome({ integrityProblems, metrics, scoreDelta, coverage }) {
  if (integrityProblems.length > 0) {
    return {
      status: "unresolved",
      label: "Unresolved comparison",
      summary: integrityProblems.join(" "),
      reasons: integrityProblems,
    };
  }

  const metricDeltas = metrics
    .map((metric) => metric.percentagePointDelta)
    .filter((delta) => delta !== null);
  const changes = [scoreDelta, ...metricDeltas, coverage.percentagePointDelta]
    .filter((delta) => delta !== null);
  const hasImprovement = changes.some((delta) => delta > 0);
  const hasRegression = changes.some((delta) => delta < 0);

  if (hasImprovement && hasRegression) {
    const regressions = metrics.filter((metric) => metric.direction === "regressed");
    const regressionNames = regressions.map((metric) => metric.name);
    return {
      status: "mixed",
      label: "Mixed result",
      summary: makeMixedSummary(scoreDelta, regressionNames),
      reasons: regressionNames.map((name) => `${name} regressed.`),
    };
  }

  if (hasRegression) {
    const regressedNames = metrics
      .filter((metric) => metric.direction === "regressed")
      .map((metric) => metric.name);
    return {
      status: "unresolved",
      label: "Unresolved comparison",
      summary: `The displayed evidence includes declines${regressedNames.length ? ` in ${regressedNames.join(", ")}` : ""}; this sample does not support an improved result.`,
      reasons: regressedNames.map((name) => `${name} regressed.`),
    };
  }

  if (hasImprovement) {
    return {
      status: "improved",
      label: "Improved",
      summary: scoreDelta > 0
        ? `The score increased by ${scoreDelta} percentage points, with no displayed metric or coverage regression.`
        : "The displayed metrics improved without a score or coverage regression.",
      reasons: [],
    };
  }

  return {
    status: "unresolved",
    label: "Unresolved comparison",
    summary: "The displayed scores, metrics, and coverage show no measurable change.",
    reasons: ["No measured difference supports an improvement claim."],
  };
}

/** makeMixedSummary names regressions beside any score gain so the headline cannot conceal them. */
function makeMixedSummary(scoreDelta, regressionNames) {
  const scoreChange = scoreDelta > 0
    ? `The updated score rose by ${scoreDelta} percentage points`
    : "The score did not rise";
  return regressionNames.length
    ? `${scoreChange}, but ${regressionNames.join(" and ")} regressed. The higher score does not erase those changes.`
    : `${scoreChange}, while the evidence shows a decline in another displayed measure.`;
}

/** getPassPercentage compares unlike denominators fairly by comparing rates as well as counts. */
function getPassPercentage(metric) {
  return metric && metric.attempted > 0
    ? percentage(metric.passed, metric.attempted)
    : null;
}

/** getDelta returns null when either side cannot be compared. */
function getDelta(originalValue, updatedValue) {
  return originalValue === null || updatedValue === null
    ? null
    : Math.round((updatedValue - originalValue) * 100) / 100;
}

/** percentage normalizes scores and rates to the same whole-percentage precision as reports. */
function percentage(passed, attempted) {
  return Math.round((passed / attempted) * 1000) / 10;
}
