import {
  getAssessmentScope,
  validateTargetUrl,
} from "./assessment.mjs";
import { WHOLE_SITE_SAMPLE } from "./sample-report.mjs";

const form = document.querySelector("#assessment-form");
const targetInput = document.querySelector("#target-url");
const goalInput = document.querySelector("#assessment-goal");
const simulationInput = document.querySelector("#simulation-mode");
const targetError = document.querySelector("#target-error");
const goalError = document.querySelector("#goal-error");
const scopeStatus = document.querySelector("#scope-status");
const scopeChip = document.querySelector("#scope-chip");
const report = document.querySelector("#sample-report");
const reportHeading = document.querySelector("#report-heading");
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
  setError(goalInput, goalError, "");
}

/** renderOrderedActions shows the bounded keyboard action sequence from the representative sample. */
function renderOrderedActions() {
  const list = document.querySelector("#action-list");
  const fragment = document.createDocumentFragment();

  for (const action of WHOLE_SITE_SAMPLE.orderedActions) {
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
    outcome.textContent = action.outcome === "passed" ? "Check passed" : "Check failed";
    topLine.append(key, target, outcome);

    const result = document.createElement("p");
    result.textContent = action.result;
    item.append(topLine, result);
    fragment.append(item);
  }

  list.replaceChildren(fragment);
}

/** renderSampleFacts fills report copy, links, and illustrative evidence from the representative sample record. */
function renderSampleFacts() {
  const sample = WHOLE_SITE_SAMPLE;
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

  const referenceLink = document.querySelector("#wcag-reference-link");
  referenceLink.href = sample.wcagReference.url;
  document.querySelector("#wcag-reference-label").textContent = sample.wcagReference.label;

  const warningList = document.querySelector("#warning-list");
  const warningItems = document.createDocumentFragment();
  for (const warning of sample.warnings) {
    const item = document.createElement("li");
    item.textContent = warning;
    warningItems.append(item);
  }
  warningList.replaceChildren(warningItems);

  const screenshot = document.querySelector("#sample-screenshot");
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
function renderFocusObservations() {
  const body = document.querySelector("#focus-table-body");
  const fragment = document.createDocumentFragment();

  for (const observation of WHOLE_SITE_SAMPLE.focusObservations) {
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
function renderRecoveryEvidence() {
  const list = document.querySelector("#recovery-list");
  const fragment = document.createDocumentFragment();

  for (const evidence of WHOLE_SITE_SAMPLE.recoveryEvidence) {
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
function renderEvidenceReferences() {
  const explanationList = document.querySelector("#explanation-evidence");
  const fixReferences = document.querySelector("#fix-evidence-references");
  const listFragment = document.createDocumentFragment();
  const fixFragment = document.createDocumentFragment();

  for (const [index, reference] of WHOLE_SITE_SAMPLE.evidenceReferences.entries()) {
    const item = document.createElement("li");
    item.append(createEvidenceLink(reference), document.createTextNode(` ${reference.label}`));
    listFragment.append(item);

    if (index > 0) {
      fixFragment.append(document.createTextNode(index === WHOLE_SITE_SAMPLE.evidenceReferences.length - 1 ? ", and " : ", "));
    }
    fixFragment.append(createEvidenceLink(reference));
  }

  explanationList.replaceChildren(listFragment);
  fixReferences.replaceChildren(fixFragment);
}

/** renderScoreAndMetrics uses one sample record for the score formula and all named metric values. */
function renderScoreAndMetrics() {
  const score = WHOLE_SITE_SAMPLE.score;
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
  for (const metric of WHOLE_SITE_SAMPLE.metrics) {
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
function prepareSampleRecord(context) {
  const record = {
    ...WHOLE_SITE_SAMPLE,
    isRepresentativeSample: true,
    recordNote: "This example record is not the result of a live browser assessment.",
    configuredContext: context,
  };
  const file = new Blob([JSON.stringify(record, null, 2)], {
    type: "application/json",
  });

  if (recordUrl) URL.revokeObjectURL(recordUrl);
  recordUrl = URL.createObjectURL(file);
  const downloadLink = document.querySelector("#download-record");
  downloadLink.href = recordUrl;
  downloadLink.download = `${WHOLE_SITE_SAMPLE.runId.toLowerCase()}.json`;
}

/** updateReportContext copies validated settings into every report field that presents them. */
function updateReportContext(context) {
  for (const [field, value] of Object.entries(context)) {
    const elements = report.querySelectorAll(`[data-report-context="${field}"]`);
    for (const element of elements) element.textContent = value;
  }
}

/** showSampleReport reveals the labeled sample after validation and never starts a browser run. */
function showSampleReport() {
  const normalizedUrl = validateTargetUrl(targetInput.value).normalizedUrl;
  const simulationMode = simulationInput.checked;
  const context = {
    targetUrl: normalizedUrl,
    assessmentScope: WHOLE_SITE_SAMPLE.scope,
    goal: WHOLE_SITE_SAMPLE.goal,
    simulationMode,
  };

  updateReportContext({
    target: normalizedUrl,
    simulationMode: simulationMode ? "On" : "Off",
  });

  prepareSampleRecord(context);
  report.hidden = false;
  reportHeading.focus({ preventScroll: true });
  reportHeading.scrollIntoView({ behavior: "auto", block: "start" });
}

/** handleAssessmentSubmit validates the local target before allowing the whole-site sample preview. */
function handleAssessmentSubmit(event) {
  event.preventDefault();
  setError(targetInput, targetError, "");
  setError(goalInput, goalError, "");

  const validation = validateTargetUrl(targetInput.value);
  if (!validation.valid) {
    setError(targetInput, targetError, validation.message);
    targetInput.focus();
    return;
  }

  if (getAssessmentScope(goalInput.value) !== "whole-site") {
    setError(
      goalInput,
      goalError,
      "This preview contains a whole-site sample only. Clear the goal to view it; no goal-focused sample is available here.",
    );
    goalInput.focus();
    return;
  }

  showSampleReport();
}

/** clearTargetValidationError removes stale feedback once the target input changes. */
function clearTargetValidationError() {
  setError(targetInput, targetError, "");
}

form.addEventListener("submit", handleAssessmentSubmit);
targetInput.addEventListener("input", clearTargetValidationError);
goalInput.addEventListener("input", updateScopePreview);
targetInput.value = WHOLE_SITE_SAMPLE.target;
document.querySelector("#recognized-target").textContent = WHOLE_SITE_SAMPLE.target;

renderOrderedActions();
renderSampleFacts();
renderFocusObservations();
renderRecoveryEvidence();
renderEvidenceReferences();
renderScoreAndMetrics();
updateScopePreview();
