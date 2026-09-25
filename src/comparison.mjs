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

const TERMINAL_STATUS_LABELS = Object.freeze({
  COMPLETED: "Completed",
  BLOCKED: "Blocked",
  INCONCLUSIVE: "Inconclusive",
  AGENT_FAILED: "Agent failed",
});

/** formatTerminalStatus maps internal state tokens to a constrained human-readable vocabulary. */
export function formatTerminalStatus(status) {
  return Object.hasOwn(TERMINAL_STATUS_LABELS, status)
    ? TERMINAL_STATUS_LABELS[status]
    : "Unknown";
}

/** formatCount keeps visible run and assessment counts grammatically correct. */
export function formatCount(count, unit) {
  if (!Number.isInteger(count) || count < 0) return `an unknown number of ${unit}s`;
  return `${count} ${unit}${count === 1 ? "" : "s"}`;
}

const EVIDENCE_COLLECTION_DESCRIPTORS = [
  {
    kind: "action",
    isAssessment: true,
    recordsFrom: (report) => report.orderedActions ?? [],
    keyForRecord: (action) => `${normalizeEvidenceText(action.key)}|${normalizeEvidenceText(action.target)}`,
    fields: [
      { name: "result", value: (action) => action.result },
      { name: "outcome", value: (action) => action.outcome },
    ],
  },
  {
    kind: "focus",
    isAssessment: true,
    recordsFrom: (report) => report.focusObservations ?? [],
    keyForRecord: (observation) => `${normalizeEvidenceText(observation.target)}|${normalizeEvidenceText(observation.role)}`,
    fields: [
      { name: "indicator", value: (observation) => observation.indicator },
      { name: "outcome", value: (observation) => observation.outcome },
    ],
  },
  {
    kind: "recovery",
    recordsFrom: (report) => report.recoveryEvidence ?? [],
    keyForRecord: (record) => normalizeEvidenceText(record.id),
    fields: [{ name: "text", value: (record) => record.text }],
  },
  {
    kind: "screenshot",
    recordsFrom: (report) => report.screenshot ? [report.screenshot] : [],
    keyForRecord: () => "version-screenshot",
    fields: [
      { name: "title", value: (screenshot) => screenshot.title },
      { name: "description", value: (screenshot) => screenshot.description },
      { name: "siteName", value: (screenshot) => screenshot.siteName },
      { name: "navigation", value: (screenshot) => JSON.stringify(screenshot.navigation) },
    ],
  },
  {
    kind: "reference",
    recordsFrom: (report) => report.evidenceReferences ?? [],
    keyForRecord: (reference) => normalizeEvidenceText(reference.id),
    fields: [{ name: "label", value: (reference) => reference.label }],
  },
];

/** buildSiteComparison compares one report or aligned report runs under shared settings. */
export function buildSiteComparison(original, updated) {
  const originalRuns = Array.isArray(original) ? original : [original];
  const updatedRuns = Array.isArray(updated) ? updated : [updated];

  const oneRunSettings = originalRuns[0]?.assessmentSettings;
  const updatedOneRunSettings = updatedRuns[0]?.assessmentSettings;
  if (originalRuns.length === 1
    && updatedRuns.length === 1
    && hasSupportedConsistency(oneRunSettings)
    && hasSupportedConsistency(updatedOneRunSettings)
    && oneRunSettings.runsPerVersion === 1
    && updatedOneRunSettings.runsPerVersion === 1) {
    const comparison = buildSingleSiteComparison(originalRuns[0], updatedRuns[0]);
    return {
      ...comparison,
      runs: { original: originalRuns, updated: updatedRuns },
      runSummaries: {
        original: originalRuns.map(summarizeRun),
        updated: updatedRuns.map(summarizeRun),
      },
      runComparisons: [{ runNumber: 1, ...comparison }],
      evidenceByRun: [{ runNumber: 1, evidence: comparison.evidence }],
      score: {
        ...comparison.score,
        original: aggregateScores(originalRuns),
        updated: aggregateScores(updatedRuns),
      },
    };
  }

  return buildRepeatedSiteComparison(originalRuns, updatedRuns);
}

/** buildSingleSiteComparison retains the established one-run comparison behavior. */
function buildSingleSiteComparison(original, updated) {
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
  const evidence = compareEvidence(original, updated);
  const everyMetricComparable = metrics.length > 0
    && metrics.every((metric) => metric.percentagePointDelta !== null);
  const integrityProblems = [
    ...settingDifferences.map((field) => `The versions use different ${field} settings.`),
    ...(!hasSupportedConsistency(original.assessmentSettings)
      ? ["The comparison consistency setting and run count are not a supported pair."]
      : []),
    ...collectReportIntegrityProblems(original, "original"),
    ...collectReportIntegrityProblems(updated, "updated"),
    ...(!metricNamesMatch ? ["The versions do not contain the same named metrics."] : []),
    ...(!everyMetricComparable ? ["At least one named metric has insufficient check data to compare."] : []),
  ];
  const outcome = chooseOutcome({
    integrityProblems,
    metrics,
    scoreDelta,
    coverage,
    evidence,
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
    evidence,
    integrityProblems,
    outcome,
  };
}

/** hasSupportedConsistency keeps the displayed level tied to its promised run count. */
function hasSupportedConsistency(settings = {}) {
  return CONSISTENCY_RUN_COUNTS[settings.consistencyLevel] === settings.runsPerVersion;
}

export const CONSISTENCY_RUN_COUNTS = Object.freeze({ Low: 1, Medium: 2, High: 3 });

/** buildRepeatedSiteComparison summarizes averages while retaining each source run and report. */
function buildRepeatedSiteComparison(originalRuns, updatedRuns) {
  const allRuns = [...originalRuns, ...updatedRuns];
  const firstReport = allRuns[0] ?? {};
  const settings = { ...(firstReport.assessmentSettings ?? {}) };
  const pairCount = Math.min(originalRuns.length, updatedRuns.length);
  const runComparisons = Array.from({ length: pairCount }, (_, index) => ({
    runNumber: index + 1,
    ...buildSingleSiteComparison(originalRuns[index], updatedRuns[index]),
  }));
  const settingDifferences = [...new Set(allRuns.flatMap((report) => (
    findSettingDifferences(settings, report.assessmentSettings)
  )))];
  const metrics = aggregateMetrics(originalRuns, updatedRuns);
  const integrityProblems = collectRepeatedIntegrityProblems({
    originalRuns,
    updatedRuns,
    allRuns,
    settings,
    settingDifferences,
    metrics,
  });
  const score = {
    original: aggregateScores(originalRuns),
    updated: aggregateScores(updatedRuns),
  };
  score.deltaPercentagePoints = getDelta(score.original.averagePercentage, score.updated.averagePercentage);
  const coverage = aggregateCoverage(originalRuns, updatedRuns);
  const evidenceByRun = runComparisons.map(({ runNumber, evidence: runEvidence }) => ({
    runNumber,
    evidence: runEvidence,
  }));
  const evidence = mergeRepeatedEvidence(evidenceByRun);
  const outcome = chooseRepeatedOutcome({
    integrityProblems,
    metrics,
    scoreDelta: score.deltaPercentagePoints,
    coverage,
    evidence,
  });

  return {
    original: originalRuns[0] ?? null,
    updated: updatedRuns[0] ?? null,
    runs: { original: originalRuns, updated: updatedRuns },
    runSummaries: {
      original: originalRuns.map(summarizeRun),
      updated: updatedRuns.map(summarizeRun),
    },
    runComparisons,
    settings,
    settingDifferences,
    score,
    metrics,
    coverage,
    evidence,
    evidenceByRun,
    integrityProblems,
    outcome,
  };
}

/** collectRepeatedIntegrityProblems names incomplete or mismatched runs instead of hiding them. */
function collectRepeatedIntegrityProblems({
  originalRuns,
  updatedRuns,
  allRuns,
  settings,
  settingDifferences,
  metrics,
}) {
  const problems = [
    ...settingDifferences.map((field) => `The runs use different ${field} settings.`),
    ...(!hasSupportedConsistency(settings)
      ? ["The comparison consistency setting and run count are not a supported pair."]
      : []),
    ...(originalRuns.length !== updatedRuns.length
      ? ["The original and updated versions have different numbers of runs."]
      : []),
    ...(settings.runsPerVersion !== originalRuns.length || settings.runsPerVersion !== updatedRuns.length
      ? [`The selected ${settings.consistencyLevel ?? "consistency"} level expects ${formatCount(settings.runsPerVersion, "run")} per version, but the reports do not match.`]
      : []),
  ];
  const firstMetrics = allRuns[0]?.metrics;
  if (allRuns.some((report) => !haveSameMetricNames(firstMetrics, report.metrics))) {
    problems.push("The runs do not contain the same named metrics.");
  }
  if (metrics.length === 0 || metrics.some(({ direction }) => direction === "unavailable")) {
    problems.push("At least one named metric has insufficient repeated-run data to compare.");
  }
  problems.push(
    ...originalRuns.flatMap((report, index) => collectReportIntegrityProblems(report, "original", index + 1)),
    ...updatedRuns.flatMap((report, index) => collectReportIntegrityProblems(report, "updated", index + 1)),
  );
  return [...new Set(problems)];
}

/** summarizeRun keeps terminal state, score availability, agent failures, and warnings attached to a run. */
function summarizeRun(report) {
  return {
    runId: report.runId,
    terminalStatus: report.terminalStatus,
    score: getReportScore(report),
    coverage: report.coverage,
    agentFailures: [...(report.agentFailures ?? [])],
    warnings: [...(report.warnings ?? [])],
  };
}

/** aggregateScores averages each recorded percentage and separately exposes its observed range. */
function aggregateScores(reports) {
  const scores = reports.map(getReportScore);
  const scored = scores.filter(({ percentage: value }) => value !== null);
  const percentages = scored.map(({ percentage: value }) => value);
  const averagePercentage = average(percentages);
  const range = percentages.length > 0
    ? { minimum: Math.min(...percentages), maximum: Math.max(...percentages) }
    : null;

  return {
    passed: sumKnownValues(scored.map(({ passed }) => passed)),
    attempted: sumKnownValues(scored.map(({ attempted }) => attempted)),
    percentage: averagePercentage,
    averagePercentage,
    range,
    scoredRuns: scored.length,
    totalRuns: reports.length,
    unscoredRuns: reports.length - scored.length,
  };
}

/** aggregateMetrics compares each named metric across every run and marks missing measurements unavailable. */
function aggregateMetrics(originalRuns, updatedRuns) {
  const names = [...new Set([...originalRuns, ...updatedRuns].flatMap((report) => (
    Array.isArray(report.metrics) ? report.metrics.map(({ name }) => name) : []
  )))];

  return names.map((name) => {
    const original = aggregateMetric(name, originalRuns);
    const updated = aggregateMetric(name, updatedRuns);
    const complete = original.scoredRuns === original.totalRuns
      && updated.scoredRuns === updated.totalRuns;
    const percentagePointDelta = complete
      ? getDelta(original.averagePercentage, updated.averagePercentage)
      : null;
    return {
      name,
      original: { ...original, percentage: complete ? original.averagePercentage : null },
      updated: { ...updated, percentage: complete ? updated.averagePercentage : null },
      passedDelta: complete ? updated.passed - original.passed : null,
      attemptedDelta: complete ? updated.attempted - original.attempted : null,
      percentagePointDelta,
      direction: percentagePointDelta === null
        ? "unavailable"
        : percentagePointDelta > 0
          ? "improved"
          : percentagePointDelta < 0
            ? "regressed"
            : "unchanged",
    };
  });
}

/** aggregateMetric returns averages only when every run recorded that named metric. */
function aggregateMetric(name, reports) {
  const records = reports.map((report) => report.metrics?.find((metric) => metric.name === name));
  const scored = records.filter((record) => getPassPercentage(record) !== null);
  return {
    passed: sumKnownValues(scored.map(({ passed }) => passed)),
    attempted: sumKnownValues(scored.map(({ attempted }) => attempted)),
    averagePercentage: average(scored.map(getPassPercentage)),
    scoredRuns: scored.length,
    totalRuns: reports.length,
  };
}

/** aggregateCoverage shows mean coverage while its run count makes missing observations explicit. */
function aggregateCoverage(originalRuns, updatedRuns) {
  const aggregateVersion = (reports) => {
    const measured = reports.filter((report) => isValidCoverage(report.coverageStats));
    const checked = average(measured.map(({ coverageStats }) => coverageStats.checked));
    const total = average(measured.map(({ coverageStats }) => coverageStats.total));
    const percentageValue = average(measured.map(({ coverageStats }) => percentage(
      coverageStats.checked,
      coverageStats.total,
    )));
    return {
      label: measured.length === reports.length
        ? `Average ${formatAverage(checked)} of ${formatAverage(total)} declared checks across ${formatCount(reports.length, "run")}`
        : `Coverage recorded for ${measured.length} of ${formatCount(reports.length, "run")}`,
      checked,
      total,
      percentage: measured.length === reports.length ? percentageValue : null,
      measuredRuns: measured.length,
      totalRuns: reports.length,
    };
  };
  const original = aggregateVersion(originalRuns);
  const updated = aggregateVersion(updatedRuns);
  const comparable = original.percentage !== null && updated.percentage !== null;
  return {
    original,
    updated,
    checkedDelta: comparable ? getDelta(original.checked, updated.checked) : null,
    totalDelta: comparable ? getDelta(original.total, updated.total) : null,
    percentagePointDelta: comparable ? getDelta(original.percentage, updated.percentage) : null,
    comparable,
  };
}

/** mergeRepeatedEvidence adds run numbers so every evidence difference links to its own report. */
function mergeRepeatedEvidence(evidenceByRun) {
  const collectionNames = [
    "assessmentChanges",
    "persistentFailures",
    "additionalUpdatedFailures",
    "unpairedOriginalFailures",
    "supportingChanges",
  ];
  const merged = Object.fromEntries(collectionNames.map((name) => [name, []]));
  for (const { runNumber, evidence } of evidenceByRun) {
    for (const name of collectionNames) {
      merged[name].push(...evidence[name].map((entry) => ({ ...entry, runNumber })));
    }
    for (const [field, sourceField] of [
      ["addedAgentFailures", "addedAgentFailures"],
      ["resolvedAgentFailures", "resolvedAgentFailures"],
      ["addedWarnings", "addedWarnings"],
      ["resolvedWarnings", "resolvedWarnings"],
    ]) {
      merged[field] ??= [];
      merged[field].push(...evidence[sourceField].map((message) => ({ message, runNumber })));
    }
  }
  return merged;
}

/** chooseRepeatedOutcome states metric divergence even when another run is inconclusive. */
function chooseRepeatedOutcome({ integrityProblems, metrics, scoreDelta, coverage, evidence }) {
  const improved = metrics.filter(({ direction }) => direction === "improved").map(({ name }) => name);
  const regressed = metrics.filter(({ direction }) => direction === "regressed").map(({ name }) => name);
  if (improved.length > 0 && regressed.length > 0) {
    const incomplete = integrityProblems.length > 0
      ? ` ${integrityProblems.join(" ")}`
      : "";
    return {
      status: "mixed",
      label: "Mixed result",
      summary: `Mixed result: ${improved.join(", ")} improved while ${regressed.join(", ")} regressed.${incomplete}`,
      reasons: [
        ...improved.map((name) => `${name} improved.`),
        ...regressed.map((name) => `${name} regressed.`),
        ...integrityProblems,
      ],
    };
  }
  return chooseOutcome({ integrityProblems, metrics, scoreDelta, coverage, evidence });
}

/** average rounds to one decimal place and returns null when no run has a comparable value. */
function average(values) {
  if (values.length === 0) return null;
  return Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 10) / 10;
}

/** sumKnownValues avoids turning unavailable report counts into zeroes. */
function sumKnownValues(values) {
  return values.length > 0 ? values.reduce((sum, value) => sum + value, 0) : null;
}

/** formatAverage keeps decimal coverage counts honest without trailing zeroes. */
function formatAverage(value) {
  return String(value);
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

/** collectReportIntegrityProblems applies the same per-report trust checks to both comparison modes. */
function collectReportIntegrityProblems(report, version, runNumber) {
  const reportName = runNumber === undefined
    ? `${version} report`
    : `${version} run ${runNumber}`;
  const problems = [];
  if (!reportMatchesSettings(report)) {
    problems.push(`The ${reportName} does not match its declared assessment settings.`);
  }
  if (report.terminalStatus !== "COMPLETED") {
    problems.push(`The ${reportName} is ${formatTerminalStatus(report.terminalStatus).toLowerCase()}.`);
  }
  if (!metricsAreInternallyConsistent(report)) {
    problems.push(`The ${reportName} metric totals do not match its reported score counts.`);
  }
  if (!reportScoreMatchesCounts(report)) {
    problems.push(`The ${reportName} score does not match its reported check counts.`);
  }
  if (getReportScore(report).percentage === null) {
    problems.push(`The ${reportName} has no score to compare.`);
  }
  if (!isValidCoverage(report.coverageStats)) {
    problems.push(`The ${reportName} has no valid coverage counts.`);
  }
  return problems;
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

/** compareEvidence applies one descriptor-driven path to assessment and supporting evidence collections. */
function compareEvidence(original, updated) {
  const collections = EVIDENCE_COLLECTION_DESCRIPTORS.map((descriptor) => (
    compareEvidenceCollection(original, updated, descriptor)
  ));
  const assessmentCollections = collections.filter(({ isAssessment }) => isAssessment);
  const supportingCollections = collections.filter(({ isAssessment }) => !isAssessment);

  return {
    assessmentChanges: assessmentCollections.flatMap(toAssessmentChanges),
    persistentFailures: assessmentCollections.flatMap(({ persistentFailures }) => persistentFailures),
    additionalUpdatedFailures: assessmentCollections.flatMap(({ additionalFailures }) => additionalFailures),
    unpairedOriginalFailures: assessmentCollections.flatMap(({ unpairedFailures }) => unpairedFailures),
    supportingChanges: supportingCollections.flatMap(toSupportingChanges),
    addedAgentFailures: findUnmatchedText(original.agentFailures, updated.agentFailures),
    resolvedAgentFailures: findUnmatchedText(updated.agentFailures, original.agentFailures),
    addedWarnings: findUnmatchedText(original.warnings, updated.warnings),
    resolvedWarnings: findUnmatchedText(updated.warnings, original.warnings),
  };
}

/** toAssessmentChanges keeps non-failure assessment records visible beside matched changes and failure summaries. */
function toAssessmentChanges(collection) {
  return [
    ...collection.changes.map((change) => ({ ...change, change: "changed" })),
    ...collection.added
      .filter(({ record }) => record.outcome !== "failed")
      .map(({ record }) => ({ kind: collection.kind, change: "added", record })),
    ...collection.removed
      .filter(({ record }) => record.outcome !== "failed")
      .map(({ record }) => ({ kind: collection.kind, change: "removed", record })),
  ];
}

/** compareEvidenceCollection aligns records once and derives changed, added, removed, and failed states. */
function compareEvidenceCollection(originalReport, updatedReport, descriptor) {
  const originalRecords = descriptor.recordsFrom(originalReport);
  const updatedRecords = descriptor.recordsFrom(updatedReport);
  const originalByKey = new Map(originalRecords.map((record) => [descriptor.keyForRecord(record), record]));
  const updatedByKey = new Map(updatedRecords.map((record) => [descriptor.keyForRecord(record), record]));
  const changes = [];
  const removed = [];
  const persistentFailures = [];
  const unpairedFailures = [];

  for (const original of originalRecords) {
    const key = descriptor.keyForRecord(original);
    const updated = updatedByKey.get(key);
    if (!updated) {
      removed.push({ kind: descriptor.kind, record: original });
      if (descriptor.isAssessment && original.outcome === "failed") {
        unpairedFailures.push({ kind: descriptor.kind, target: original.target, record: original });
      }
      continue;
    }

    const changedFields = descriptor.fields
      .filter(({ value }) => value(original) !== value(updated))
      .map(({ name }) => name);
    if (changedFields.length > 0) {
      changes.push({
        kind: descriptor.kind,
        target: original.target ?? updated.target,
        original,
        updated,
        changedFields,
        ...(descriptor.isAssessment
          ? { direction: compareEvidenceOutcome(original, updated) }
          : {}),
      });
    }

    if (descriptor.isAssessment && original.outcome === "failed" && updated.outcome === "failed") {
      persistentFailures.push({ kind: descriptor.kind, target: original.target, original, updated });
    }
  }

  const added = [];
  const additionalFailures = [];
  for (const updated of updatedRecords) {
    if (originalByKey.has(descriptor.keyForRecord(updated))) continue;
    added.push({ kind: descriptor.kind, record: updated });
    if (descriptor.isAssessment && updated.outcome === "failed") {
      additionalFailures.push({ kind: descriptor.kind, target: updated.target, record: updated });
    }
  }

  return {
    kind: descriptor.kind,
    isAssessment: descriptor.isAssessment === true,
    changes,
    added,
    removed,
    persistentFailures,
    additionalFailures,
    unpairedFailures,
  };
}

/** toSupportingChanges turns non-assessment records into a uniform user-facing change list. */
function toSupportingChanges(collection) {
  return [
    ...collection.changes.map((change) => ({ ...change, change: "changed" })),
    ...collection.added.map(({ record }) => ({ kind: collection.kind, change: "added", record })),
    ...collection.removed.map(({ record }) => ({ kind: collection.kind, change: "removed", record })),
  ];
}

/** compareEvidenceOutcome assigns direction only when both records carry explicit pass/fail evidence. */
function compareEvidenceOutcome(original, updated) {
  if (!["passed", "failed"].includes(original.outcome)
    || !["passed", "failed"].includes(updated.outcome)) return "unresolved";
  if (original.outcome === updated.outcome) return "changed";
  return updated.outcome === "passed" ? "improved" : "regressed";
}

/** findUnmatchedText lists agent failures or warnings added to one version without interpreting their meaning. */
function findUnmatchedText(baselineItems = [], changedItems = []) {
  return changedItems.filter((item) => !baselineItems.includes(item));
}

/** normalizeEvidenceText makes record matching stable across harmless casing and spacing differences. */
function normalizeEvidenceText(value = "") {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
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
function chooseOutcome({ integrityProblems, metrics, scoreDelta, coverage, evidence }) {
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
  const evidenceChanges = [
    ...evidence.assessmentChanges,
  ];
  const evidenceDirections = [
    ...evidenceChanges.map(({ direction }) => direction),
    ...evidence.additionalUpdatedFailures.map(() => "regressed"),
  ];
  const hasImprovement = changes.some((delta) => delta > 0)
    || evidenceDirections.includes("improved");
  const hasRegression = changes.some((delta) => delta < 0)
    || evidenceDirections.includes("regressed");
  const evidenceIsUnresolved = evidence.unpairedOriginalFailures.length > 0
    || evidenceDirections.includes("unresolved");

  if (hasImprovement && (hasRegression || evidence.persistentFailures.length > 0)) {
    const regressions = metrics.filter((metric) => metric.direction === "regressed");
    const regressionNames = regressions.map((metric) => metric.name);
    const additionalFailures = evidence.additionalUpdatedFailures;
    const unresolvedTargets = [...new Set(evidence.unpairedOriginalFailures.map(({ target }) => target))];
    const failedTargets = [...new Set(additionalFailures.map(({ target }) => target))];
    const persistentTargets = [...new Set(evidence.persistentFailures.map(({ target }) => target))];
    return {
      status: "mixed",
      label: "Mixed result",
      summary: makeMixedSummary(
        scoreDelta,
        {
          regressionNames,
          additionalFailures,
          unpairedOriginalFailures: evidence.unpairedOriginalFailures,
          persistentFailures: evidence.persistentFailures,
        },
      ),
      reasons: [
        ...regressionNames.map((name) => `${name} regressed.`),
        ...failedTargets.map((target) => `Updated evidence records an additional failed check at ${target}.`),
        ...persistentTargets.map((target) => `A failed check at ${target} remains failed in both reports.`),
        ...unresolvedTargets.map((target) => `The original failed check at ${target} has no matching updated observation.`),
      ],
    };
  }

  if (evidenceIsUnresolved) {
    return {
      status: "unresolved",
      label: "Unresolved comparison",
      summary: "Some original failed evidence has no matching updated observation, so the comparison cannot tell whether it changed.",
      reasons: evidence.unpairedOriginalFailures.map(({ target }) => `The original failed check at ${target} was not repeated in the updated report.`),
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

  if (evidence.persistentFailures.length > 0) {
    const persistentTargets = [...new Set(evidence.persistentFailures.map(({ target }) => target))];
    return {
      status: "unresolved",
      label: "Unresolved comparison",
      summary: `No displayed change supports an improvement; failed checks at ${persistentTargets.join(" and ")} remain failed in both reports.`,
      reasons: persistentTargets.map((target) => `A failed check at ${target} remains failed in both reports.`),
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

/** makeMixedSummary names measured regressions and incomplete evidence beside any score gain. */
function makeMixedSummary(scoreDelta, {
  regressionNames = [],
  additionalFailures = [],
  unpairedOriginalFailures = [],
  persistentFailures = [],
}) {
  const scoreChange = scoreDelta > 0
    ? `The updated score rose by ${scoreDelta} percentage points`
    : "The score did not rise";
  const failedTargets = [...new Set(additionalFailures.map(({ target }) => target))];
  const regressions = [
    ...(regressionNames.length ? [`${regressionNames.join(" and ")} regressed`] : []),
    ...(failedTargets.length ? [`updated evidence adds an unmatched failed check at ${failedTargets.join(" and ")}`] : []),
  ];
  const regressionSummary = regressions.length ? `, but ${regressions.join("; ")}` : "";
  const regressionCaveat = regressions.length ? " The higher score does not erase those changes." : "";
  const persistentTargets = [...new Set(persistentFailures.map(({ target }) => target))];
  const persistentSummary = persistentTargets.length
    ? ` Failed checks at ${persistentTargets.join(" and ")} remain failed in both reports.`
    : "";
  const unresolvedTargets = [...new Set(unpairedOriginalFailures.map(({ target }) => target))];
  const unresolvedSummary = unresolvedTargets.length
    ? ` Original failed evidence at ${unresolvedTargets.join(" and ")} has no matching updated observation, so its outcome is unknown.`
    : "";
  return `${scoreChange}${regressionSummary}.${regressionCaveat}${persistentSummary}${unresolvedSummary}`;
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
