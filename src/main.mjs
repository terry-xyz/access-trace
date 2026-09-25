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

function setError(input, container, message) {
  container.textContent = message;
  container.hidden = message === "";
  input.setAttribute("aria-invalid", String(message !== ""));
}

function updateScopePreview() {
  const scope = getAssessmentScope(goalInput.value);
  const isWholeSite = scope === "whole-site";
  scopeStatus.textContent = isWholeSite
    ? "Whole-site assessment selected"
    : "Goal-focused assessment selected";
  scopeChip.textContent = isWholeSite ? "Whole site" : "Goal focused";
  setError(goalInput, goalError, "");
}

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

function renderFocusObservations() {
  const body = document.querySelector("#focus-table-body");
  const fragment = document.createDocumentFragment();

  for (const observation of WHOLE_SITE_SAMPLE.focusObservations) {
    const row = document.createElement("tr");
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

function renderRecoveryEvidence() {
  const list = document.querySelector("#recovery-list");
  const fragment = document.createDocumentFragment();

  WHOLE_SITE_SAMPLE.recoveryEvidence.forEach((evidence, index) => {
    const item = document.createElement("li");
    if (index === 0) item.id = "REC-01";
    item.textContent = evidence;
    fragment.append(item);
  });

  list.replaceChildren(fragment);
}

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
    value.append(
      document.createTextNode(String(metric.passed)),
      Object.assign(document.createElement("span"), {
        textContent: ` / ${metric.attempted}`,
      }),
    );
    const track = document.createElement("div");
    track.className = "metric-track";
    track.setAttribute("aria-hidden", "true");
    const fill = document.createElement("span");
    fill.style.width = `${metric.attempted === 0 ? 0 : (metric.passed / metric.attempted) * 100}%`;
    track.append(fill);
    card.append(name, value, track);
    fragment.append(card);
  }
  grid.replaceChildren(fragment);
}

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

function showSampleReport() {
  const normalizedUrl = validateTargetUrl(targetInput.value).normalizedUrl;
  const simulationMode = simulationInput.checked;
  const context = {
    targetUrl: normalizedUrl,
    assessmentScope: "whole-site",
    goal: null,
    simulationMode,
  };

  for (const selector of ["#report-target", "#details-target"]) {
    document.querySelector(selector).textContent = normalizedUrl;
  }
  for (const selector of ["#report-scope", "#details-scope"]) {
    document.querySelector(selector).textContent = "Whole site";
  }
  for (const selector of ["#report-simulation", "#details-simulation"]) {
    document.querySelector(selector).textContent = simulationMode ? "On" : "Off";
  }

  prepareSampleRecord(context);
  report.hidden = false;
  reportHeading.focus({ preventScroll: true });
  reportHeading.scrollIntoView({ behavior: "auto", block: "start" });
}

form.addEventListener("submit", (event) => {
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
});

targetInput.addEventListener("input", () => setError(targetInput, targetError, ""));
goalInput.addEventListener("input", updateScopePreview);

renderOrderedActions();
renderFocusObservations();
renderRecoveryEvidence();
renderScoreAndMetrics();
updateScopePreview();
