import {
  getAssessmentScope,
  validateAssessmentGoal,
  validateTargetUrl,
} from "./assessment.mjs";
import { buildSiteComparison } from "./comparison.mjs";
import {
  AGENT_UPDATED_GOAL_FOCUSED_SAMPLE,
  AGENT_UPDATED_WHOLE_SITE_SAMPLE,
  GOAL_FOCUSED_SAMPLE,
  WHOLE_SITE_SAMPLE,
} from "./sample-report.mjs";

const form = document.querySelector("#assessment-form");
const targetInput = document.querySelector("#target-url");
const goalInput = document.querySelector("#assessment-goal");
const simulationInput = document.querySelector("#simulation-mode");
const targetError = document.querySelector("#target-error");
const goalError = document.querySelector("#goal-error");
const scopeStatus = document.querySelector("#scope-status");
const scopeChip = document.querySelector("#scope-chip");
const submitLabel = document.querySelector("#submit-label");
const report = document.querySelector("#sample-report");
const reportHeading = document.querySelector("#report-heading");
const comparisonButton = document.querySelector("#view-comparison");
const comparisonSection = document.querySelector("#sample-comparison");
const comparisonHeading = document.querySelector("#comparison-heading");
let recordUrl;

/** formatScopeLabel gives a stable presentation label to the stored assessment-scope value. */
function formatScopeLabel(scope) {
  return scope === "whole-site" ? "Whole site" : "Goal focused";
}

/** setError keeps the visible message and the field's programmatic invalid state aligned. */
function setError(input, container, message) {
  container.textContent = message;
  container.hidden = message === "";
  input.setAttribute("aria-invalid", String(message !== ""));
}

/** updateScopePreview reflects the optional goal as an explicit whole-site or goal-focused choice. */
function updateScopePreview() {
  const scope = getAssessmentScope(goalInput.value);
  const isWholeSite = scope === "whole-site";
  scopeStatus.textContent = isWholeSite
    ? "Whole-site assessment selected"
    : "Goal-focused assessment selected";
  scopeChip.textContent = isWholeSite ? "Whole site" : "Goal focused";
  submitLabel.textContent = isWholeSite
    ? "View whole-site sample report"
    : "View goal-focused sample report";
  setError(goalInput, goalError, "");
  report.hidden = true;
  comparisonSection.hidden = true;
}

/** renderOrderedActions shows the bounded keyboard action sequence from the representative sample. */
function renderOrderedActions(sample) {
  const list = document.querySelector("#action-list");
  const fragment = document.createDocumentFragment();

  for (const action of sample.orderedActions) {
    const item = document.createElement("li");
    item.id = action.id;
    item.className = `action-item action-${action.outcome}`;

    const topLine = document.createElement("div");
    topLine.className = "action-topline";
    const key = document.createElement("span");
    key.className = "key-chip";
    key.textContent = action.key;
    const target = document.createElement("strong");
    target.textContent = action.target;
    const outcome = document.createElement("span");
    outcome.className = "action-outcome";
    outcome.textContent = action.outcome === "passed" ? "Website check passed" : "Website check failed";
    topLine.append(key, target, outcome);

    const result = document.createElement("p");
    result.textContent = action.result;
    item.append(topLine, result);
    fragment.append(item);
  }

  list.replaceChildren(fragment);
}

/** renderSampleFacts fills report copy, links, and illustrative evidence from the representative sample record. */
function renderSampleFacts(sample) {
  const facts = {
    terminalStatus: sample.terminalStatus,
    scopeLabel: formatScopeLabel(sample.scope),
    outcomeTitle: sample.outcomeTitle,
    coverage: sample.coverage,
    explanationTitle: sample.explanationTitle,
    explanation: sample.explanation,
    confidence: sample.confidence,
    confidenceContext: sample.confidenceContext,
    proposedFixTitle: sample.proposedFixTitle,
    proposedFix: sample.proposedFix,
    duration: sample.duration,
    interactionCount: String(sample.interactionCount),
    goalSummary: sample.goal ?? "None supplied",
    agentFailureSummary: sample.agentFailures.length
      ? sample.agentFailures.join(", ")
      : "None recorded in sample",
    screenshotTitle: `${sample.screenshot.id} · ${sample.screenshot.title}`,
    screenshotDescription: sample.screenshot.description,
  };

  for (const [field, value] of Object.entries(facts)) {
    for (const element of report.querySelectorAll(`[data-sample-fact="${field}"]`)) {
      element.textContent = value;
    }
  }

  const referenceLink = report.querySelector('[data-sample-link="wcagReference"]');
  referenceLink.href = sample.wcagReference.url;
  document.querySelector("#wcag-reference-label").textContent = sample.wcagReference.label;

  const warningList = report.querySelector('[data-sample-list="warnings"]');
  const warningItems = document.createDocumentFragment();
  for (const warning of sample.warnings) {
    const item = document.createElement("li");
    item.textContent = warning;
    warningItems.append(item);
  }
  warningList.replaceChildren(warningItems);

  const screenshot = report.querySelector("[data-sample-screenshot]");
  screenshot.id = sample.screenshot.id;
  screenshot.setAttribute("aria-label", sample.screenshot.description);
  document.querySelector("#capture-site-name").textContent = sample.screenshot.siteName;

  const navigation = document.querySelector("#capture-nav");
  const navigationItems = document.createDocumentFragment();
  for (const entry of sample.screenshot.navigation) {
    const item = document.createElement("span");
    item.textContent = entry.label;
    if (entry.focused) item.className = "capture-focused";
    navigationItems.append(item);
  }
  navigation.replaceChildren(navigationItems);
  document.querySelector("#evidence-count").textContent = `${sample.orderedActions.length} ordered sample actions`;
}

/** renderFocusObservations gives each sample row the ID used by its evidence links. */
function renderFocusObservations(sample) {
  const body = document.querySelector("#focus-table-body");
  const fragment = document.createDocumentFragment();

  for (const observation of sample.focusObservations) {
    const row = document.createElement("tr");
    row.id = observation.id;
    const referenceCell = document.createElement("td");
    const reference = document.createElement("a");
    reference.href = `#${observation.id}`;
    reference.textContent = observation.id;
    referenceCell.append(reference);

    const targetCell = document.createElement("td");
    targetCell.append(document.createTextNode(`${observation.target} · ${observation.role}`));
    const indicatorCell = document.createElement("td");
    indicatorCell.textContent = observation.indicator;
    row.append(referenceCell, targetCell, indicatorCell);
    fragment.append(row);
  }

  body.replaceChildren(fragment);
}

/** renderRecoveryEvidence attaches stable sample IDs so a reference lands on the cited recovery item. */
function renderRecoveryEvidence(sample) {
  const list = document.querySelector("#recovery-list");
  const fragment = document.createDocumentFragment();

  for (const evidence of sample.recoveryEvidence) {
    const item = document.createElement("li");
    item.id = evidence.id;
    item.textContent = evidence.text;
    fragment.append(item);
  }

  list.replaceChildren(fragment);
}

/** createEvidenceLink connects a human-readable evidence label to its in-report record. */
function createEvidenceLink(reference) {
  const link = document.createElement("a");
  link.href = `#${reference.id}`;
  link.textContent = reference.id;
  link.setAttribute("aria-label", `${reference.id}: ${reference.label}`);
  return link;
}

/** renderEvidenceReferences attaches the same sample citations to both the explanation and proposed fix. */
function renderEvidenceReferences(sample) {
  const explanationList = document.querySelector("#explanation-evidence");
  const fixReferences = document.querySelector("#fix-evidence-references");
  const listFragment = document.createDocumentFragment();
  const fixFragment = document.createDocumentFragment();

  for (const [index, reference] of sample.evidenceReferences.entries()) {
    const item = document.createElement("li");
    item.append(createEvidenceLink(reference), document.createTextNode(` ${reference.label}`));
    listFragment.append(item);

    if (index > 0) {
      fixFragment.append(document.createTextNode(index === sample.evidenceReferences.length - 1 ? ", and " : ", "));
    }
    fixFragment.append(createEvidenceLink(reference));
  }

  explanationList.replaceChildren(listFragment);
  fixReferences.replaceChildren(fixFragment);
}

/** renderScoreAndMetrics uses one sample record for the score formula and all named metric values. */
function renderScoreAndMetrics(sample) {
  const score = sample.score;
  document.querySelector("#score-percent").textContent = score.percentage ?? "—";
  const separator = document.createElement("span");
  separator.textContent = "/";
  separator.setAttribute("aria-hidden", "true");
  document.querySelector("#score-count").replaceChildren(
    document.createTextNode(`${score.passed} passed `),
    separator,
    document.createTextNode(` ${score.attempted} attempted`),
  );
  document.querySelector("#score-formula").textContent = score.percentage === null
    ? score.label
    : `${score.passed} ÷ ${score.attempted} × 100 = ${score.percentage}%`;

  const progress = document.querySelector("#score-progress");
  progress.value = score.passed;
  progress.max = score.attempted || 1;
  progress.textContent = score.percentage === null ? score.label : `${score.percentage}%`;
  progress.setAttribute("aria-label", score.label);

  const grid = document.querySelector("#metrics-grid");
  const fragment = document.createDocumentFragment();
  for (const metric of sample.metrics) {
    const card = document.createElement("div");
    card.className = "metric-card";
    const name = document.createElement("dt");
    name.textContent = metric.name;
    const value = document.createElement("dd");
    const fraction = document.createElement("span");
    fraction.textContent = ` / ${metric.attempted}`;
    value.append(document.createTextNode(String(metric.passed)), fraction);
    const track = document.createElement("div");
    track.className = "metric-track";
    track.setAttribute("aria-hidden", "true");
    const fill = document.createElement("span");
    fill.style.width = `${metric.attempted === 0 ? 0 : (metric.passed / metric.attempted) * 100}%`;
    track.append(fill);
    value.append(track);
    card.append(name, value);
    fragment.append(card);
  }
  grid.replaceChildren(fragment);
}

/** prepareSampleRecord packages the sample evidence with the current configuration without implying a live run. */
function prepareSampleRecord(sample, context) {
  const record = {
    ...sample,
    isRepresentativeSample: true,
    recordNote: "Representative report data, not a live assessment or evidence about the configured goal.",
    configuredContext: context,
  };
  const file = new Blob([JSON.stringify(record, null, 2)], {
    type: "application/json",
  });

  if (recordUrl) URL.revokeObjectURL(recordUrl);
  recordUrl = URL.createObjectURL(file);
  const downloadLink = document.querySelector("#download-record");
  downloadLink.href = recordUrl;
  downloadLink.download = `${sample.runId.toLowerCase()}.json`;
}

/** updateReportContext copies validated settings into every report field that presents them. */
function updateReportContext(context) {
  for (const [field, value] of Object.entries(context)) {
    const elements = report.querySelectorAll(`[data-report-context="${field}"]`);
    for (const element of elements) element.textContent = value;
  }
}

/** showSampleReport reveals the labeled sample after validation and never starts a browser run. */
function showSampleReport(configuration) {
  const goal = configuration.goal;
  const sample = configuration.scope === "whole-site"
    ? WHOLE_SITE_SAMPLE
    : { ...GOAL_FOCUSED_SAMPLE, goal };
  const context = {
    targetUrl: configuration.targetUrl,
    assessmentScope: sample.scope,
    goal: sample.goal,
    simulationMode: configuration.simulationMode,
  };

  updateReportContext({
    target: configuration.targetUrl,
    simulationMode: configuration.simulationMode ? "On" : "Off",
  });

  renderReportSample(sample);
  prepareSampleRecord(sample, context);
  comparisonSection.hidden = true;
  report.hidden = false;
  reportHeading.focus({ preventScroll: true });
  reportHeading.scrollIntoView({ behavior: "auto", block: "start" });
}

/** validateCurrentConfiguration applies the same target and goal boundary to reports and comparisons. */
function validateCurrentConfiguration() {
  report.hidden = true;
  comparisonSection.hidden = true;
  setError(targetInput, targetError, "");
  setError(goalInput, goalError, "");

  const validation = validateTargetUrl(targetInput.value);
  if (!validation.valid) {
    setError(targetInput, targetError, validation.message);
    targetInput.focus();
    return null;
  }

  const goalValidation = validateAssessmentGoal(goalInput.value);
  if (!goalValidation.valid) {
    setError(goalInput, goalError, goalValidation.message);
    goalInput.focus();
    return null;
  }

  return {
    targetUrl: validation.normalizedUrl,
    scope: goalValidation.scope,
    goal: goalValidation.goal || null,
    simulationMode: simulationInput.checked,
  };
}

/** handleAssessmentSubmit validates the target and goal before showing the matching sample report. */
function handleAssessmentSubmit(event) {
  event.preventDefault();
  const configuration = validateCurrentConfiguration();
  if (configuration) showSampleReport(configuration);
}

/** getComparisonSettings records every shared condition used for the two Low-consistency samples. */
function getComparisonSettings(configuration) {
  return {
    targetUrl: configuration.targetUrl,
    scope: configuration.scope,
    goal: configuration.goal,
    simulationMode: configuration.simulationMode,
    interactionProfile: "Keyboard only",
    browserConditions: "Same controlled local browser conditions",
    consistencyLevel: "Low",
    runsPerVersion: 1,
  };
}

/** createComparisonSamples gives each version the exact same configured assessment context. */
function createComparisonSamples(configuration, settings) {
  const samples = configuration.scope === "whole-site"
    ? [WHOLE_SITE_SAMPLE, AGENT_UPDATED_WHOLE_SITE_SAMPLE]
    : [GOAL_FOCUSED_SAMPLE, AGENT_UPDATED_GOAL_FOCUSED_SAMPLE];

  return samples.map((sample) => ({
    ...sample,
    goal: configuration.goal,
    assessmentSettings: settings,
  }));
}

/** handleComparisonRequest shows a validated comparison and moves focus to its result heading. */
function handleComparisonRequest() {
  const configuration = validateCurrentConfiguration();
  if (!configuration) return;

  const settings = getComparisonSettings(configuration);
  const [original, updated] = createComparisonSamples(configuration, settings);
  const comparison = buildSiteComparison(original, updated);
  renderComparison(comparison);
  report.hidden = true;
  comparisonSection.hidden = false;
  comparisonHeading.focus({ preventScroll: true });
  comparisonHeading.scrollIntoView({ behavior: "auto", block: "start" });
}

/** renderComparison puts score, metric, and coverage changes ahead of its supporting reports. */
function renderComparison(comparison) {
  const status = document.querySelector("#comparison-status");
  status.textContent = comparison.outcome.label;
  status.dataset.outcome = comparison.outcome.status;
  document.querySelector("#comparison-summary").textContent = comparison.outcome.summary;

  document.querySelector("#comparison-original-score").textContent = formatScore(comparison.score.original);
  document.querySelector("#comparison-original-count").textContent = `${comparison.score.original.passed} passed / ${comparison.score.original.attempted} attempted`;
  document.querySelector("#comparison-updated-score").textContent = formatScore(comparison.score.updated);
  document.querySelector("#comparison-updated-count").textContent = `${comparison.score.updated.passed} passed / ${comparison.score.updated.attempted} attempted`;
  document.querySelector("#comparison-score-delta").textContent = formatSigned(comparison.score.deltaPercentagePoints);
  document.querySelector("#comparison-original-coverage").textContent = comparison.coverage.original.label;
  document.querySelector("#comparison-updated-coverage").textContent = comparison.coverage.updated.label;
  document.querySelector("#comparison-coverage-delta").textContent = formatCoverageChange(comparison.coverage);

  renderComparisonMetrics(comparison.metrics);
  renderComparisonEvidence(comparison.evidence);
  renderComparisonSettings(comparison.settings);
  renderComparisonReport(
    document.querySelector("#comparison-original-report-content"),
    comparison.original,
    "original",
  );
  renderComparisonReport(
    document.querySelector("#comparison-updated-report-content"),
    comparison.updated,
    "updated",
  );
}

/** formatScore keeps a missing score explicit instead of presenting it as zero. */
function formatScore(score) {
  return score.percentage === null ? "Unavailable" : `${score.percentage}%`;
}

/** formatSigned makes direction visible in score, coverage, and metric changes. */
function formatSigned(value) {
  if (value === null) return "Not comparable";
  if (value === 0) return "No change";
  return `${value > 0 ? "+" : ""}${value}`;
}

/** formatCoverageChange keeps both coverage counts visible alongside their percentage-point change. */
function formatCoverageChange(coverage) {
  if (!coverage.comparable) return "Coverage change unavailable";
  const changed = coverage.checkedDelta === 0 && coverage.totalDelta === 0
    ? "No change in checked or declared coverage"
    : `${formatSigned(coverage.checkedDelta)} checked; ${formatSigned(coverage.totalDelta)} declared`;
  return `${changed}; ${formatSigned(coverage.percentagePointDelta)} percentage points`;
}

/** renderComparisonMetrics exposes every metric row and labels its direction in words. */
function renderComparisonMetrics(metrics) {
  const body = document.querySelector("#comparison-metrics-body");
  const fragment = document.createDocumentFragment();

  for (const metric of metrics) {
    const row = document.createElement("tr");
    const name = document.createElement("th");
    name.scope = "row";
    name.textContent = metric.name;
    const original = document.createElement("td");
    original.textContent = formatMetricValue(metric.original);
    const updated = document.createElement("td");
    updated.textContent = formatMetricValue(metric.updated);
    const change = document.createElement("td");
    change.textContent = metric.percentagePointDelta === null
      ? "Not comparable"
      : `${formatSigned(metric.passedDelta)} checks; ${formatSigned(metric.percentagePointDelta)} pp`;
    const direction = document.createElement("td");
    const directionLabel = document.createElement("span");
    directionLabel.className = "metric-direction";
    directionLabel.dataset.direction = metric.direction;
    directionLabel.textContent = metric.direction === "unavailable"
      ? "Unavailable"
      : metric.direction === "unchanged"
        ? "No change"
        : metric.direction === "improved"
          ? "Improved"
          : "Regression";
    direction.append(directionLabel);
    row.append(name, original, updated, change, direction);
    fragment.append(row);
  }

  body.replaceChildren(fragment);
}

/** formatMetricValue shows passed and attempted counts as well as the pass rate. */
function formatMetricValue(metric) {
  return metric
    ? `${metric.passed} / ${metric.attempted} (${metric.percentage ?? "—"}%)`
    : "Not recorded";
}

/** renderComparisonEvidence names aligned changes and unmatched failures before users open either report. */
function renderComparisonEvidence(evidence) {
  const list = document.querySelector("#comparison-evidence-changes");
  const fragment = document.createDocumentFragment();
  const addEvidenceItem = (text, links = []) => {
    const item = document.createElement("li");
    item.append(document.createTextNode(text));
    for (const { version, id, label } of links) {
      item.append(document.createTextNode(" "));
      const link = document.createElement("a");
      link.href = `#comparison-${version}-${id}`;
      link.textContent = label;
      link.addEventListener("click", () => {
        document.querySelector(`#comparison-${version}-report`).open = true;
      });
      item.append(link);
    }
    fragment.append(item);
  };

  for (const change of evidence.assessmentChanges) {
    if (change.kind === "action") {
      addEvidenceItem(
        `Keyboard action at ${change.target}: original “${change.original.result}” (${change.original.outcome}), updated “${change.updated.result}” (${change.updated.outcome}).`,
        [
          { version: "original", id: change.original.id, label: `Original ${change.original.id}` },
          { version: "updated", id: change.updated.id, label: `Updated ${change.updated.id}` },
        ],
      );
    } else {
      addEvidenceItem(
        `Focus observation at ${change.target}: original “${change.original.indicator}”, updated “${change.updated.indicator}” (${formatEvidenceDirection(change.direction)}).`,
        [
          { version: "original", id: change.original.id, label: `Original ${change.original.id}` },
          { version: "updated", id: change.updated.id, label: `Updated ${change.updated.id}` },
        ],
      );
    }
  }
  for (const failure of evidence.persistentFailures) {
    addEvidenceItem(
      `Both reports record a failed ${failure.kind} check at ${failure.target}.`,
      [
        { version: "original", id: failure.original.id, label: `Original ${failure.original.id}` },
        { version: "updated", id: failure.updated.id, label: `Updated ${failure.updated.id}` },
      ],
    );
  }
  for (const failure of evidence.additionalUpdatedFailures) {
    const evidenceDescription = failure.kind === "action"
      ? `keyboard action: ${failure.record.result}`
      : `focus observation: ${failure.record.indicator}`;
    addEvidenceItem(
      `Updated report adds a failed ${evidenceDescription} at ${failure.target}.`,
      [{ version: "updated", id: failure.record.id, label: `Updated ${failure.record.id}` }],
    );
  }
  for (const failure of evidence.unpairedOriginalFailures) {
    addEvidenceItem(
      `Original failed ${failure.kind} evidence at ${failure.target} has no matching updated observation; its outcome is unknown.`,
      [{ version: "original", id: failure.record.id, label: `Original ${failure.record.id}` }],
    );
  }
  for (const change of evidence.supportingChanges) {
    appendSupportingEvidenceDifference(addEvidenceItem, change);
  }
  for (const message of evidence.addedAgentFailures) {
    addEvidenceItem(`Updated report also records an agent failure: ${message}`);
  }
  for (const warning of evidence.addedWarnings) {
    addEvidenceItem(`Updated report adds a warning: ${warning}`);
  }
  for (const message of evidence.resolvedAgentFailures) {
    addEvidenceItem(`Original report records an agent failure not present in the updated report: ${message}`);
  }
  for (const warning of evidence.resolvedWarnings) {
    addEvidenceItem(`Original report adds a warning not present in the updated report: ${warning}`);
  }

  if (fragment.childNodes.length === 0) {
    const item = document.createElement("li");
    item.textContent = "No action, focus, recovery, screenshot, or citation differences were recorded.";
    fragment.append(item);
  }
  list.replaceChildren(fragment);
}

/** appendSupportingEvidenceDifference gives recovery notes, screenshots, and citations concise linked summaries. */
function appendSupportingEvidenceDifference(addEvidenceItem, change) {
  if (change.kind === "recovery") {
    if (change.change === "changed") {
      addEvidenceItem(
        `Recovery evidence ${change.original.id} changed: original “${change.original.text}”, updated “${change.updated.text}”.`,
        [
          { version: "original", id: change.original.id, label: `Original ${change.original.id}` },
          { version: "updated", id: change.updated.id, label: `Updated ${change.updated.id}` },
        ],
      );
    } else {
      const version = change.change === "added" ? "updated" : "original";
      const record = change.record;
      addEvidenceItem(
        `${version === "updated" ? "Updated" : "Original"} report ${change.change} recovery evidence ${record.id}: ${record.text}.`,
        [{ version, id: record.id, label: `${version === "updated" ? "Updated" : "Original"} ${record.id}` }],
      );
    }
    return;
  }

  if (change.kind === "reference") {
    const original = change.original;
    const updated = change.updated;
    const record = change.record;
    const links = change.change === "changed"
      ? [
        { version: "original", id: original.id, label: `Original ${original.id}` },
        { version: "updated", id: updated.id, label: `Updated ${updated.id}` },
      ]
      : [{
        version: change.change === "added" ? "updated" : "original",
        id: record.id,
        label: `${change.change === "added" ? "Updated" : "Original"} ${record.id}`,
      }];
    const description = change.change === "changed"
      ? `Citation ${original.id} changed label from “${original.label}” to “${updated.label}”.`
      : `${change.change === "added" ? "Updated" : "Original"} report ${change.change} evidence citation ${record.id}: ${record.label}.`;
    addEvidenceItem(description, links);
    return;
  }

  const original = change.original;
  const updated = change.updated;
  const record = change.record;
  const describeScreenshot = (screenshot) => (
    `${screenshot.title} for ${screenshot.siteName}; ${screenshot.description} Navigation: ${describeSampleNavigation(screenshot.navigation)}.`
  );
  if (change.change === "changed") {
    addEvidenceItem(
      `Screenshot mockup changed (${change.changedFields.join(", ")}): original ${describeScreenshot(original)}, updated ${describeScreenshot(updated)}.`,
      [
        { version: "original", id: original.id, label: `Original ${original.id}` },
        { version: "updated", id: updated.id, label: `Updated ${updated.id}` },
      ],
    );
  } else {
    const version = change.change === "added" ? "updated" : "original";
    addEvidenceItem(
      `${version === "updated" ? "Updated" : "Original"} report ${change.change} screenshot mockup ${record.id}: ${describeScreenshot(record)}.`,
      [{ version, id: record.id, label: `${version === "updated" ? "Updated" : "Original"} ${record.id}` }],
    );
  }
}

/** describeSampleNavigation distinguishes the focused sample item from other mockup navigation entries. */
function describeSampleNavigation(navigation) {
  return navigation
    .map(({ label, focused }) => `${label}${focused ? " (focused)" : ""}`)
    .join(", ");
}

/** formatEvidenceDirection gives explicit outcome changes a readable label in the evidence summary. */
function formatEvidenceDirection(direction) {
  return direction === "improved"
    ? "improved"
    : direction === "regressed"
      ? "regressed"
      : direction === "changed"
        ? "outcome unchanged"
        : "direction unresolved";
}

/** renderComparisonSettings makes the shared setup and fixed Low run count explicit. */
function renderComparisonSettings(settings) {
  const list = document.querySelector("#comparison-settings");
  const values = [
    ["Target", settings.targetUrl],
    ["Assessment scope", formatScopeLabel(settings.scope)],
    ["Goal", settings.goal ?? "None (whole-site)"],
    ["Simulation mode", settings.simulationMode ? "On" : "Off"],
    ["Interaction profile", settings.interactionProfile],
    ["Browser conditions", settings.browserConditions],
    ["Consistency", `${settings.consistencyLevel} — ${settings.runsPerVersion} assessment per version`],
  ];
  const fragment = document.createDocumentFragment();

  for (const [label, value] of values) {
    const item = document.createElement("div");
    item.className = "comparison-setting";
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value;
    item.append(term, description);
    fragment.append(item);
  }

  list.replaceChildren(fragment);
}

/** renderComparisonReport keeps all report facts and evidence available inside each version's details. */
function renderComparisonReport(container, sample, version) {
  const fragment = document.createDocumentFragment();
  const idPrefix = `comparison-${version}-`;
  const evidenceIds = getComparisonEvidenceIds(sample, idPrefix);

  appendComparisonHeading(fragment, "Report summary");
  appendComparisonParagraph(fragment, "Run", sample.runId);
  appendComparisonParagraph(fragment, "Terminal state", sample.terminalStatus);
  appendComparisonParagraph(fragment, "Assessment scope", formatScopeLabel(sample.scope));
  appendComparisonParagraph(fragment, "Target", sample.assessmentSettings.targetUrl);
  appendComparisonParagraph(fragment, "Goal", sample.assessmentSettings.goal ?? "None supplied");
  appendComparisonParagraph(fragment, "Simulation mode", sample.assessmentSettings.simulationMode ? "On" : "Off");
  appendComparisonParagraph(fragment, "Coverage", sample.coverage);
  appendComparisonParagraph(fragment, "Duration", sample.duration);
  appendComparisonParagraph(fragment, "Interaction count", String(sample.interactionCount));
  appendComparisonParagraph(fragment, "Score", `${sample.score.label} (${sample.score.percentage}%)`);
  appendComparisonParagraph(fragment, "Outcome", sample.outcomeTitle);

  appendComparisonHeading(fragment, "Named metrics");
  const metricsList = document.createElement("ul");
  for (const metric of sample.metrics) {
    const item = document.createElement("li");
    item.textContent = `${metric.name}: ${metric.passed} of ${metric.attempted} checks passed`;
    metricsList.append(item);
  }
  fragment.append(metricsList);

  appendComparisonHeading(fragment, "Explanation and proposed fix");
  appendComparisonParagraph(fragment, sample.explanationTitle, sample.explanation);
  appendComparisonParagraph(fragment, "Confidence", `${sample.confidence} — ${sample.confidenceContext}`);
  if (sample.proposedFix) {
    appendComparisonParagraph(fragment, sample.proposedFixTitle, sample.proposedFix);
  } else {
    appendComparisonParagraph(fragment, "Proposed fix", "No evidence-supported proposed fix is available.");
  }
  const reference = document.createElement("p");
  reference.className = "comparison-report-evidence";
  reference.append(document.createTextNode("WCAG context: "));
  const referenceLink = document.createElement("a");
  referenceLink.href = sample.wcagReference.url;
  referenceLink.target = "_blank";
  referenceLink.rel = "noreferrer";
  referenceLink.textContent = sample.wcagReference.label;
  reference.append(referenceLink, document.createTextNode(". This is not a conformance result."));
  fragment.append(reference);

  appendComparisonHeading(fragment, "Ordered action evidence");
  const actions = document.createElement("ol");
  for (const action of sample.orderedActions) {
    const item = document.createElement("li");
    item.id = evidenceIds.get(action.id);
    item.textContent = `${action.id} · ${action.key} · ${action.target}: ${action.result} (${action.outcome})`;
    actions.append(item);
  }
  fragment.append(actions);

  appendComparisonHeading(fragment, "Focus observations");
  const focus = document.createElement("ul");
  for (const observation of sample.focusObservations) {
    const item = document.createElement("li");
    item.id = evidenceIds.get(observation.id);
    item.textContent = `${observation.id} · ${observation.target} (${observation.role}): ${observation.indicator}`;
    focus.append(item);
  }
  fragment.append(focus);

  appendComparisonHeading(fragment, "Screenshot mockup");
  appendComparisonScreenshot(fragment, sample.screenshot, evidenceIds.get(sample.screenshot.id));

  appendComparisonHeading(fragment, "Evidence references");
  const references = document.createElement("ul");
  for (const evidenceReference of sample.evidenceReferences) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = `#${evidenceIds.get(evidenceReference.id)}`;
    link.textContent = evidenceReference.id;
    item.append(link, document.createTextNode(` ${evidenceReference.label}`));
    references.append(item);
  }
  fragment.append(references);

  appendComparisonHeading(fragment, "Recovery evidence");
  appendComparisonList(fragment, sample.recoveryEvidence, "text", evidenceIds);
  appendComparisonHeading(fragment, "Agent failures");
  appendComparisonList(fragment, sample.agentFailures, null);
  appendComparisonHeading(fragment, "Warnings");
  appendComparisonList(fragment, sample.warnings, null);

  container.replaceChildren(fragment);
}

/** appendComparisonScreenshot preserves the sample capture's site, navigation, and focused item in each report. */
function appendComparisonScreenshot(parent, sampleScreenshot, evidenceId) {
  const focusedItems = sampleScreenshot.navigation
    .filter((entry) => entry.focused)
    .map(({ label }) => label);
  const navigationSummary = describeSampleNavigation(sampleScreenshot.navigation);
  const figure = document.createElement("figure");
  figure.id = evidenceId;
  figure.className = "sample-capture comparison-report-screenshot";
  figure.setAttribute("role", "img");
  figure.setAttribute(
    "aria-label",
    `${sampleScreenshot.title}. ${sampleScreenshot.description} Site: ${sampleScreenshot.siteName}. Navigation: ${navigationSummary}.`,
  );

  const chrome = document.createElement("div");
  chrome.className = "capture-chrome";
  chrome.setAttribute("aria-hidden", "true");
  for (let dot = 0; dot < 3; dot += 1) chrome.append(document.createElement("span"));
  const host = document.createElement("i");
  host.textContent = "sample.local";
  chrome.append(host);

  const content = document.createElement("div");
  content.className = "capture-content";
  content.setAttribute("aria-hidden", "true");
  const brand = document.createElement("div");
  brand.className = "capture-brand";
  const siteName = document.createElement("span");
  siteName.textContent = sampleScreenshot.siteName;
  const brandMark = document.createElement("span");
  brandMark.textContent = "▰";
  brand.append(siteName, brandMark);

  const navigation = document.createElement("div");
  navigation.className = "capture-nav";
  for (const entry of sampleScreenshot.navigation) {
    const item = document.createElement("span");
    item.textContent = entry.label;
    if (entry.focused) item.className = "capture-focused";
    navigation.append(item);
  }

  const shortLine = document.createElement("div");
  shortLine.className = "capture-line capture-line-short";
  const line = document.createElement("div");
  line.className = "capture-line";
  const form = document.createElement("div");
  form.className = "capture-form";
  form.append(document.createElement("span"), document.createElement("span"), document.createElement("b"));
  content.append(brand, navigation, shortLine, line, form);

  const caption = document.createElement("figcaption");
  caption.textContent = `${sampleScreenshot.id} · ${sampleScreenshot.title} · ${sampleScreenshot.description}`;
  const focusSummary = document.createElement("p");
  focusSummary.className = "comparison-screenshot-focus-summary";
  focusSummary.textContent = focusedItems.length
    ? `Illustrated keyboard focus: ${focusedItems.join(", ")}.`
    : "No focused navigation item is shown in this sample mockup.";

  figure.append(chrome, content, focusSummary, caption);
  parent.append(figure);
}

/** getComparisonEvidenceIds gives each embedded report unique in-page anchors. */
function getComparisonEvidenceIds(sample, prefix) {
  const ids = new Map();
  const records = [
    ...sample.orderedActions,
    ...sample.focusObservations,
    ...sample.recoveryEvidence,
    sample.screenshot,
  ];
  for (const record of records) ids.set(record.id, `${prefix}${record.id}`);
  return ids;
}

/** appendComparisonHeading keeps each evidence section's name visible to keyboard and screen-reader users. */
function appendComparisonHeading(parent, text) {
  const heading = document.createElement("h4");
  heading.textContent = text;
  parent.append(heading);
}

/** appendComparisonParagraph creates text-only report facts without injecting sample HTML. */
function appendComparisonParagraph(parent, label, value) {
  const paragraph = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = `${label}: `;
  paragraph.append(strong, document.createTextNode(value));
  parent.append(paragraph);
}

/** appendComparisonList preserves recovery and warning records with their stable evidence anchors. */
function appendComparisonList(parent, items, textKey, evidenceIds = new Map()) {
  const list = document.createElement("ul");
  if (items.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "None recorded in this representative sample.";
    list.append(empty);
  }
  for (const entry of items) {
    const item = document.createElement("li");
    if (textKey) {
      item.id = evidenceIds.get(entry.id);
      item.textContent = `${entry.id}: ${entry[textKey]}`;
    } else {
      item.textContent = entry;
    }
    list.append(item);
  }
  parent.append(list);
}

/** renderReportSample keeps every visible fact and evidence item sourced from the chosen sample record. */
function renderReportSample(sample) {
  renderOrderedActions(sample);
  renderSampleFacts(sample);
  renderFocusObservations(sample);
  renderRecoveryEvidence(sample);
  renderEvidenceReferences(sample);
  renderScoreAndMetrics(sample);
}

/** clearTargetValidationError removes stale feedback once the target input changes. */
function clearTargetValidationError() {
  setError(targetInput, targetError, "");
  report.hidden = true;
  comparisonSection.hidden = true;
}

/** clearStaleSampleReport prevents an old preview from appearing to describe changed simulation settings. */
function clearStaleSampleReport() {
  report.hidden = true;
  comparisonSection.hidden = true;
}

form.addEventListener("submit", handleAssessmentSubmit);
comparisonButton.addEventListener("click", handleComparisonRequest);
targetInput.addEventListener("input", clearTargetValidationError);
goalInput.addEventListener("input", updateScopePreview);
simulationInput.addEventListener("change", clearStaleSampleReport);
targetInput.value = WHOLE_SITE_SAMPLE.target;
document.querySelector("#recognized-target").textContent = WHOLE_SITE_SAMPLE.target;

renderReportSample(WHOLE_SITE_SAMPLE);
updateScopePreview();
