import {
  getAssessmentScope,
  validateAssessmentGoal,
  validateTargetUrl,
} from "./assessment.mjs";
import { CONSISTENCY_RUN_COUNTS, summarizeLiveComparisonCounts } from "./live-comparison.mjs";

const form = document.querySelector("#assessment-form");
const targetInput = document.querySelector("#target-url");
const builtInTargetInput = document.querySelector("#built-in-target");
const recognizedTarget = document.querySelector("#recognized-target");
const goalInput = document.querySelector("#assessment-goal");
const simulationInput = document.querySelector("#simulation-mode");
const localHtmlFileInput = document.querySelector("#local-html-file");
const localHtmlStatus = document.querySelector("#local-html-status");
const loadLocalHtmlButton = document.querySelector("#load-local-html");
const liveAssessmentButton = document.querySelector("#start-live-assessment");
const cancelLiveAssessmentButton = document.querySelector("#cancel-live-assessment");
const liveAssessmentSection = document.querySelector("#live-assessment");
const liveAssessmentStatus = document.querySelector("#live-assessment-status");
const liveRecordDownload = document.querySelector("#download-live-record");
const liveRecordDetails = document.querySelector("#live-record-details");
const liveRecordJson = document.querySelector("#live-record-json");
const liveTerminal = document.querySelector("#live-terminal");
const liveResult = document.querySelector("#live-result");
const liveRunReport = document.querySelector("#live-run-report");
const runReportTemplate = document.querySelector("#run-report-template");
const liveRunProgress = document.querySelector("#live-run-progress");
const liveProgressLabel = document.querySelector("#live-progress-label");
const liveProgressPercent = document.querySelector("#live-progress-percent");
const terminalLog = document.querySelector("#terminal-log");
const consistencyInput = document.querySelector("#comparison-consistency");
const targetError = document.querySelector("#target-error");
const goalError = document.querySelector("#goal-error");
const scopeStatus = document.querySelector("#scope-status");
const scopeChip = document.querySelector("#scope-chip");
const submitLabel = document.querySelector("#submit-label");
const comparisonButton = document.querySelector("#view-comparison");
const comparisonSection = document.querySelector("#comparison-section");
const comparisonHeading = document.querySelector("#comparison-heading");
const comparisonCancelButton = document.querySelector("#cancel-comparison-run");
const comparisonProgress = document.querySelector("#comparison-progress");
const comparisonProgressLabel = document.querySelector("#comparison-progress-label");
const comparisonProgressCount = document.querySelector("#comparison-progress-count");
const comparisonProgressTotal = document.querySelector("#comparison-progress-total");
const comparisonRunStatus = document.querySelector("#comparison-run-status");
const setupSection = document.querySelector("#setup");
const newAssessmentButton = document.querySelector("#new-assessment");
const navButtons = {
  setup: document.querySelector("#nav-setup"),
  comparison: document.querySelector("#nav-comparison"),
};
let liveRecordUrl;
let reportRenderSequence = 0;
let activeLiveRunId = null;
let activeRunContext = null;
let workflowInProgress = false;

/** setActiveView keeps one focused app screen visible without scrolling the document. */
function setActiveView(view) {
  setupSection.hidden = view !== "setup";
  comparisonSection.hidden = view !== "comparison";
  liveAssessmentSection.hidden = view !== "live";
  for (const [key, button] of Object.entries(navButtons)) {
    if (key === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
}

/** setWorkflowBusy locks settings and navigation for the complete create, execute, and review flow. */
function setWorkflowBusy(busy) {
  workflowInProgress = busy;
  for (const control of form.querySelectorAll("input, select, textarea, button")) {
    control.disabled = busy;
  }
  for (const button of Object.values(navButtons)) button.disabled = busy;
}

/** setCancelableRun exposes cancellation only for the currently executing browser journey. */
function setCancelableRun(runId, context) {
  activeLiveRunId = runId;
  activeRunContext = runId ? context : null;
  cancelLiveAssessmentButton.hidden = !runId || context !== "single";
  comparisonCancelButton.hidden = !runId || context !== "comparison";
  cancelLiveAssessmentButton.disabled = false;
  comparisonCancelButton.disabled = false;
}

/** clearCancelableRun removes the stop target as soon as the stored journey reaches a terminal state. */
function clearCancelableRun(runId) {
  if (activeLiveRunId !== runId) return;
  setCancelableRun(null, null);
}

/** waitForRunTerminal watches durable run status while execute remains open for the evidence review. */
async function waitForRunTerminal(runId, shouldContinue, onTerminal) {
  while (shouldContinue()) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1500);
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`, {
        signal: controller.signal,
      });
      if (response.ok) {
        const record = await response.json();
        if (record && typeof record.status === "string" && record.status !== "IN_PROGRESS") {
          onTerminal(record.status);
          return;
        }
      }
    } catch {
      // A failed status poll does not change the execute request or its returned record.
    } finally {
      clearTimeout(timeout);
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
}

/** executeRun watches terminal browser status independently from the final review response. */
async function executeRun(runId, context) {
  let requestSettled = false;
  const monitor = waitForRunTerminal(runId, () => !requestSettled, () => {
    clearCancelableRun(runId);
    if (context === "single") {
      liveAssessmentStatus.textContent = "Browser run finished. Evidence review is running…";
      setRunStage(90, "Reviewing evidence", "Browser run saved; preparing its evidence review.");
    } else {
      comparisonRunStatus.textContent = "Browser run finished. Its evidence review is running…";
    }
  });

  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/execute`, {
      method: "POST",
    });
    const result = await readResponseJson(response);
    return { response, result };
  } finally {
    requestSettled = true;
    await monitor;
    clearCancelableRun(runId);
  }
}

/** readResponseJson tolerates a non-JSON server failure so each comparison slot can continue. */
async function readResponseJson(response) {
  try {
    const value = await response.json();
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}

/** responseError uses only the server's bounded public message, with a safe operation fallback. */
function responseError(result, fallback) {
  return typeof result?.error?.message === "string" && result.error.message.trim()
    ? result.error.message.slice(0, 300)
    : fallback;
}

/** setRunStage reports completed workflow steps; page coverage appears in the final report. */
function setRunStage(value, label, message) {
  liveRunProgress.value = value;
  liveRunProgress.setAttribute("aria-valuetext", `${value}% · ${label}`);
  liveProgressPercent.textContent = String(value);
  liveProgressLabel.textContent = label;
  if (message) {
    const entry = document.createElement("li");
    const time = document.createElement("time");
    time.textContent = new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date());
    const text = document.createElement("span");
    text.textContent = message;
    entry.append(time, text);
    terminalLog.append(entry);
  }
}

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
  scopeStatus.textContent = isWholeSite ? "Whole page" : "Goal focused";
  scopeChip.textContent = isWholeSite ? "Whole site" : "Goal focused";
  submitLabel.textContent = "Start assessment";
  setError(goalInput, goalError, "");
  if (!workflowInProgress) setActiveView("setup");
}

/** validateCurrentConfiguration applies the same target and goal boundary to reports and comparisons. */
function validateCurrentConfiguration() {
  if (workflowInProgress) return null;
  comparisonSection.hidden = true;
  setError(targetInput, targetError, "");
  setError(goalInput, goalError, "");

  const validation = validateTargetUrl(targetInput.value, window.location.origin);
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

/** handleAssessmentSubmit starts the configured live assessment. */
function handleAssessmentSubmit(event) {
  event.preventDefault();
  void handleLiveAssessment();
}

/** handleLocalHtmlUpload stores one self-contained page on this server and selects its opaque route. */
async function handleLocalHtmlUpload() {
  const file = localHtmlFileInput.files?.[0];
  if (!file) {
    localHtmlStatus.textContent = "Choose one .html or .htm file first.";
    return;
  }
  if (!/\.html?$/i.test(file.name)) {
    localHtmlStatus.textContent = "Choose a standalone .html or .htm file.";
    return;
  }
  if (file.size > 1024 * 1024) {
    localHtmlStatus.textContent = "The HTML file must be 1 MB or smaller.";
    return;
  }

  loadLocalHtmlButton.disabled = true;
  localHtmlStatus.textContent = "Loading the local HTML file…";
  try {
    const response = await fetch("/api/sites", {
      method: "POST",
      headers: { "Content-Type": "text/html; charset=utf-8" },
      body: file,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || "The HTML file could not be loaded.");

    targetInput.value = result.targetUrl;
    builtInTargetInput.value = "";
    updateRecognizedTargetLabel();
    clearTargetValidationError();
    localHtmlStatus.textContent = `Loaded ${file.name}. This local page is selected as the target.`;
  } catch (error) {
    localHtmlStatus.textContent = error instanceof Error
      ? error.message
      : "The HTML file could not be loaded.";
  } finally {
    loadLocalHtmlButton.disabled = false;
  }
}

/** selectBuiltInTarget keeps demo selection on the same server origin as the app. */
function selectBuiltInTarget() {
  if (!builtInTargetInput.value) return;
  targetInput.value = `${window.location.origin}${builtInTargetInput.value}`;
  updateRecognizedTargetLabel();
  clearTargetValidationError();
}

/** updateRecognizedTargetLabel mirrors the active built-in or uploaded route without retaining stale text. */
function updateRecognizedTargetLabel() {
  const validation = validateTargetUrl(targetInput.value, window.location.origin);
  recognizedTarget.textContent = validation.valid
    ? validation.normalizedUrl
    : "Choose a built-in demo or load a local HTML file";
}

/** setField writes plain text into one report instance without relying on document-wide IDs. */
function setField(report, field, value) {
  const element = report.querySelector(`[data-field="${field}"]`);
  if (element) element.textContent = value;
}

/** recordedNumber distinguishes a recorded zero from a missing statistic. */
function recordedNumber(value) {
  return Number.isFinite(value) && value >= 0 ? value : null;
}

/** formatRunStatus keeps unfamiliar terminal tokens visible instead of guessing their meaning. */
function formatRunStatus(status) {
  if (typeof status !== "string" || status.trim() === "") return "Not recorded";
  const words = status.replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** focusDescription uses only the focus fields captured in the supplied run record. */
function focusDescription(focus) {
  if (!focus || typeof focus !== "object") return "";
  const name = focus.accessibleName || focus.stableId || focus.tag;
  const role = focus.role || focus.tag;
  if (name && role && name !== role) return `${name} (${role})`;
  return name || role || "";
}

/** evidenceLocator accepts only the citation kinds persisted by the review boundary. */
function evidenceLocator(reference) {
  if (!reference || typeof reference !== "object") return null;
  if (["action", "observation", "recovery"].includes(reference.kind)
    && Number.isInteger(reference.sequence)
    && reference.sequence > 0) {
    const locator = `${reference.kind}:${reference.sequence}`;
    return reference.id === locator ? locator : null;
  }
  if (reference.kind === "stopping-screenshot"
    && reference.id === "stopping-screenshot") {
    return "stopping-screenshot";
  }
  return null;
}

/** anchorIdFor namespaces each evidence locator inside its own mounted report. */
function anchorIdFor(reportToken, locator) {
  return `${reportToken}-${locator.replaceAll(":", "-")}`;
}

/** actionDescription states the saved key, type count, field, and action status. */
function actionDescription(action) {
  const parts = [];
  if (action.kind === "type") {
    if (recordedNumber(action.characterCount) !== null) {
      parts.push(`${action.characterCount} characters typed`);
    }
    if (typeof action.field === "string" && action.field) parts.push(`field: ${action.field}`);
  } else if (typeof action.key === "string" && action.key) {
    parts.push(`key: ${action.key}`);
  } else if (typeof action.kind === "string" && action.kind) {
    parts.push(`action: ${action.kind}`);
  }
  if (typeof action.status === "string" && action.status) parts.push(`status: ${action.status}`);
  const focusBefore = focusDescription(action.focusBefore);
  if (focusBefore) parts.push(`focus before: ${focusBefore}`);
  return parts.join(" · ") || JSON.stringify(action);
}

/** observationDescription reports captured page and focus fields without adding an assessment. */
function observationDescription(observation) {
  const parts = [];
  if (typeof observation.title === "string" && observation.title) parts.push(observation.title);
  const focus = focusDescription(observation.focus);
  if (focus) parts.push(`focus: ${focus}`);
  if (typeof observation.url === "string" && observation.url) parts.push(observation.url);
  if (observation.success && typeof observation.success.matched === "boolean") {
    const condition = observation.success.condition || "Success condition";
    parts.push(`${condition}: ${observation.success.matched ? "matched" : "not matched"}`);
  }
  return parts.join(" · ") || JSON.stringify(observation);
}

/** recoveryDescription presents the sanitized recovery record's recorded checks and actions. */
function recoveryDescription(recovery) {
  const parts = [];
  if (typeof recovery.kind === "string" && recovery.kind) parts.push(recovery.kind);
  if (Array.isArray(recovery.attemptedActivations) && recovery.attemptedActivations.length) {
    parts.push(`attempted activations: ${recovery.attemptedActivations.join(", ")}`);
  }
  const checks = [
    ["activationFocusConsistent", "Activation focus consistent"],
    ["unchangedProgress", "Progress unchanged"],
    ["sameSubmitFocus", "Submit focus unchanged"],
    ["localFocusRecovery", "Local focus recovery"],
    ["wholePageWrapped", "Whole-page traversal wrapped"],
    ["successMatched", "Success condition matched"],
  ];
  for (const [field, label] of checks) {
    if (typeof recovery[field] === "boolean") parts.push(`${label}: ${recovery[field] ? "yes" : "no"}`);
  }
  if (Array.isArray(recovery.actions)) {
    for (const action of recovery.actions) {
      const step = [action.key, action.status].filter((value) => typeof value === "string" && value);
      if (step.length) parts.push(step.join(" · "));
    }
  }
  return parts.join(" · ") || JSON.stringify(recovery);
}

/** renderRunReport mounts one record into a reusable template and scopes every citation to it. */
function renderRunReport(record, root) {
  root.replaceChildren(runReportTemplate.content.cloneNode(true));
  const report = root.querySelector(".run-report");
  const evidence = record?.evidenceHandoff ?? {};
  const stats = evidence.stats ?? {};
  const assessment = evidence.assessment ?? {};
  const stopping = evidence.stopping?.point ?? record?.stoppingPoint ?? {};
  const reporting = evidence.reporting ?? {};
  const actions = Array.isArray(evidence.actions)
    ? evidence.actions
    : Array.isArray(record?.actions) ? record.actions : [];
  const observations = Array.isArray(evidence.observations)
    ? evidence.observations
    : Array.isArray(record?.observations) ? record.observations : [];
  const recoveries = Array.isArray(evidence.terminal?.recoveryEvidence)
    ? evidence.terminal.recoveryEvidence
    : Array.isArray(record?.recoveryEvidence) ? record.recoveryEvidence : [];
  const warnings = Array.isArray(evidence.terminal?.warnings)
    ? evidence.terminal.warnings
    : Array.isArray(record?.warnings) ? record.warnings : [];
  const status = stats.terminalStatus ?? record?.status;
  const statusLabel = formatRunStatus(status);
  const reportToken = `${root.id || "run-report"}-${++reportRenderSequence}`;
  const anchors = new Map();

  setField(report, "heading", typeof record?.id === "string" && record.id
    ? `Run ${record.id}`
    : "Assessment result");
  setField(report, "status-label", statusLabel);
  setField(report, "outcome-heading", statusLabel);
  report.querySelector('[data-field="status"]').dataset.outcome = (
    typeof status === "string" ? status.toLowerCase() : "unknown"
  );

  const durationMs = recordedNumber(stats.durationMs ?? record?.durationMs);
  setField(report, "duration", durationMs === null ? "Not recorded" : `${(durationMs / 1000).toFixed(1)} seconds`);
  const interactions = recordedNumber(stats.interactionCount ?? record?.interactionCount);
  setField(report, "interactions", interactions === null ? "Not recorded" : `${interactions} keyboard interactions`);
  const rawActionCount = Array.isArray(record?.actions) ? record.actions.length : null;
  const actionCount = recordedNumber(stats.actionCount ?? rawActionCount);
  setField(report, "action-count", actionCount === null ? "Not recorded" : `${actionCount} actions`);

  const coverage = stats.coverage ?? stopping.coverage ?? evidence.progress?.coverage;
  const coverageObserved = recordedNumber(coverage?.controlsObserved ?? coverage?.areasObserved);
  const coverageExpected = recordedNumber(coverage?.controlsExpected ?? coverage?.areasExpected);
  const coverageUnit = Number.isFinite(coverage?.controlsExpected) || Number.isFinite(coverage?.controlsObserved)
    ? "controls observed"
    : "areas observed";
  const coverageText = coverageObserved !== null && coverageExpected !== null
    ? `${coverageObserved} of ${coverageExpected} ${coverageUnit}`
    : typeof coverage?.status === "string" && coverage.status
      ? `Status: ${coverage.status}`
      : "Not available";
  setField(report, "coverage", coverageText);

  const goalProgress = stats.goalProgress ?? stopping.goalProgress ?? evidence.progress?.goal;
  const completedFields = recordedNumber(goalProgress?.completedFields);
  const expectedFields = recordedNumber(goalProgress?.expectedFields);
  const goalProgressText = completedFields !== null && expectedFields !== null
    ? `${completedFields} of ${expectedFields} goal fields completed`
    : typeof goalProgress?.status === "string" && goalProgress.status
      ? `Status: ${goalProgress.status}`
      : "Not available";
  setField(report, "goal-progress", goalProgressText);

  const successCondition = stopping.successCondition || assessment.successCondition || record?.successCondition;
  const successMatched = stopping.successMatched ?? record?.successMatched;
  const successText = typeof successCondition === "string" && successCondition
    ? `${successCondition} · ${successMatched === true ? "Reached" : successMatched === false ? "Not reached" : "Result not recorded"}`
    : "Not configured";
  setField(report, "success", successText);
  setField(report, "target", assessment.targetUrl || record?.targetUrl || "Not recorded");
  setField(report, "goal", assessment.goal || record?.goal || "No goal configured");

  const screenshotRef = evidence.stopping?.screenshotRef ?? record?.stoppingScreenshotRef;
  if (typeof screenshotRef === "string" && screenshotRef) {
    const screenshot = report.querySelector('[data-field="screenshot"]');
    screenshot.hidden = false;
    screenshot.id = anchorIdFor(reportToken, "stopping-screenshot");
    screenshot.dataset.evidenceLocator = "stopping-screenshot";
    screenshot.textContent = `Stopping screenshot reference: ${screenshotRef}`;
    anchors.set("stopping-screenshot", screenshot);
  }

  const appendEvidence = (field, records, kind, describe, getSequence) => {
    const list = report.querySelector(`[data-field="${field}"]`);
    const fragment = document.createDocumentFragment();
    records.forEach((entry, index) => {
      const sequence = getSequence(entry, index);
      const locator = sequence === null ? null : `${kind}:${sequence}`;
      const item = document.createElement("li");
      if (locator) {
        item.id = anchorIdFor(reportToken, locator);
        item.dataset.evidenceLocator = locator;
        anchors.set(locator, item);
      }
      item.textContent = `${sequence === null ? "" : `${sequence}. `}${describe(entry)}`;
      fragment.append(item);
    });
    list.replaceChildren(fragment);
  };
  appendEvidence("actions", actions, "action", actionDescription, (action) => (
    Number.isInteger(action.sequence) && action.sequence > 0 ? action.sequence : null
  ));
  appendEvidence("observations", observations, "observation", observationDescription, (_, index) => index + 1);
  appendEvidence("recoveries", recoveries, "recovery", recoveryDescription, (recovery) => (
    Number.isInteger(recovery.sequence) && recovery.sequence > 0 ? recovery.sequence : null
  ));

  const warningList = report.querySelector('[data-field="warnings"]');
  const warningItems = document.createDocumentFragment();
  for (const warning of warnings) {
    const item = document.createElement("li");
    item.textContent = typeof warning === "string"
      ? warning
      : warning?.message || warning?.kind || JSON.stringify(warning);
    warningItems.append(item);
  }
  warningList.replaceChildren(warningItems);
  report.querySelector('[data-field="warnings-block"]').hidden = warnings.length === 0;

  const availableReview = reporting.status === "available"
    && typeof reporting.explanation === "string"
    && reporting.explanation.trim() !== "";
  setField(report, "review-status", availableReview
    ? "Review available"
    : reporting.status === "pending" ? "Review pending" : "Review unavailable");
  const explanation = report.querySelector('[data-field="review-explanation"]');
  explanation.hidden = !availableReview;
  explanation.textContent = availableReview ? reporting.explanation : "";
  const confidence = report.querySelector('[data-field="confidence"]');
  confidence.hidden = !availableReview || !["low", "medium", "high"].includes(reporting.confidence);
  confidence.textContent = confidence.hidden ? "" : `Confidence: ${reporting.confidence}`;

  const fixBlock = report.querySelector('[data-field="fix-block"]');
  fixBlock.hidden = !availableReview;
  if (availableReview) {
    const proposedFix = typeof reporting.proposedFix === "string" && reporting.proposedFix.trim()
      ? reporting.proposedFix
      : "No evidence-supported fix available";
    setField(report, "fix", proposedFix);
  }

  const referencesList = report.querySelector('[data-field="review-references"]');
  const referenceItems = document.createDocumentFragment();
  const references = availableReview && Array.isArray(reporting.evidenceReferences)
    ? reporting.evidenceReferences
    : [];
  for (const reference of references) {
    const locator = evidenceLocator(reference);
    const target = locator ? anchors.get(locator) : null;
    if (!target) continue;
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = `#${target.id}`;
    link.textContent = locator;
    link.addEventListener("click", () => {
      const details = target.closest("details");
      if (details) details.open = true;
    });
    item.append(link);
    referenceItems.append(item);
  }
  referencesList.replaceChildren(referenceItems);
  referencesList.hidden = referencesList.childElementCount === 0;
}

/** handleLiveAssessment creates and executes one real run, then exposes its redacted JSON record. */
async function handleLiveAssessment() {
  const configuration = validateCurrentConfiguration();
  if (!configuration) return;

  setActiveView("live");
  setWorkflowBusy(true);
  liveTerminal.hidden = false;
  liveResult.hidden = true;
  terminalLog.replaceChildren();
  setRunStage(25, "Settings checked", "Local target and assessment settings checked.");
  liveAssessmentStatus.textContent = "Creating a fresh local run…";
  liveRecordDownload.hidden = true;
  liveRecordDetails.hidden = true;
  try {
    const createResponse = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        targetUrl: configuration.targetUrl,
        goal: configuration.goal,
        simulationMode: configuration.simulationMode,
      }),
    });
    const created = await readResponseJson(createResponse);
    if (!createResponse.ok) {
      throw new Error(responseError(created, "The run could not be created."));
    }
    if (typeof created.id !== "string" || !created.id) {
      throw new Error("The server did not return a run identifier.");
    }

    setRunStage(50, "Run created", "Local run record created.");
    setCancelableRun(created.id, "single");
    setRunStage(75, "Assessment running", "Isolated keyboard assessment started.");
    liveAssessmentStatus.textContent = "The isolated browser is checking the page…";
    const { response: executeResponse, result } = await executeRun(created.id, "single");
    if (!executeResponse.ok) {
      throw new Error(responseError(result, "The run could not be completed."));
    }
    if (!result || typeof result.id !== "string" || !result.id) {
      throw new Error("The server did not return a completed run record.");
    }

    setRunStage(100, "Result saved", `Run saved with status ${result.status}.`);
    liveAssessmentStatus.textContent = `Run ${result.id} finished: ${result.status}.`;
    renderRunReport(result, liveRunReport);
    const serialized = JSON.stringify(result, null, 2);
    liveRecordJson.textContent = serialized;
    if (liveRecordUrl) URL.revokeObjectURL(liveRecordUrl);
    liveRecordUrl = URL.createObjectURL(new Blob([serialized], { type: "application/json" }));
    liveRecordDownload.href = liveRecordUrl;
    liveRecordDownload.download = `access-trace-${result.id}.json`;
    liveRecordDownload.hidden = false;
    liveRecordDetails.hidden = false;
    liveTerminal.hidden = true;
    liveResult.hidden = false;
    liveRunReport.querySelector('[data-field="heading"]').focus({ preventScroll: true });
  } catch (error) {
    liveAssessmentStatus.textContent = error instanceof Error
      ? error.message
      : "The local assessment could not be completed.";
    setRunStage(liveRunProgress.value, "Run needs attention", "The run did not return a completed result.");
  } finally {
    if (activeLiveRunId) clearCancelableRun(activeLiveRunId);
    setWorkflowBusy(false);
  }
}

/** handleCancelLiveAssessment cancels only the captured browser run while it remains in progress. */
async function handleCancelLiveAssessment() {
  const runId = activeLiveRunId;
  if (!runId) return;

  const context = activeRunContext;
  const button = context === "comparison" ? comparisonCancelButton : cancelLiveAssessmentButton;
  button.disabled = true;
  setRunStatus(context, "Requesting cancellation…");
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
    });
    const result = await readResponseJson(response);
    if (!response.ok) {
      throw new Error(responseError(result, "The run could not be cancelled."));
    }
    if (activeLiveRunId === runId) {
      setRunStatus(context, "Cancellation requested. Waiting for the browser run to finish…");
    }
  } catch (error) {
    if (activeLiveRunId === runId) {
      setRunStatus(context, error instanceof Error ? error.message : "The run could not be cancelled.");
      button.disabled = false;
    }
  }
}

/** setRunStatus routes cancellation and progress messages to the currently visible workflow. */
function setRunStatus(context, message) {
  if (context === "comparison") comparisonRunStatus.textContent = message;
  else liveAssessmentStatus.textContent = message;
}

/** getComparisonSettings records the shared scope and configured real-run count. */
function getComparisonSettings(configuration) {
  const consistencyLevel = consistencyInput.value;
  return {
    targetUrl: "Built-in broken and fixed demos",
    scope: configuration.scope,
    goal: configuration.goal,
    simulationMode: configuration.simulationMode,
    consistencyLevel,
    runsPerVersion: CONSISTENCY_RUN_COUNTS[consistencyLevel],
  };
}

/** handleComparisonRequest runs paired demo slots in order and keeps each response isolated. */
async function handleComparisonRequest() {
  const configuration = validateCurrentConfiguration();
  if (!configuration) return;

  const settings = getComparisonSettings(configuration);
  const totalSlots = settings.runsPerVersion * 2;
  const slots = { broken: [], fixed: [] };
  const containers = {
    broken: document.querySelector("#comparison-broken-runs"),
    fixed: document.querySelector("#comparison-fixed-runs"),
  };

  let processed = 0;
  try {
    setActiveView("comparison");
    setWorkflowBusy(true);
    comparisonHeading.focus({ preventScroll: true });
    containers.broken.replaceChildren();
    containers.fixed.replaceChildren();
    renderComparisonSettings(settings);
    comparisonProgress.max = totalSlots;
    comparisonProgress.value = 0;
    comparisonProgressCount.textContent = "0";
    comparisonProgressTotal.textContent = String(totalSlots);
    comparisonProgress.setAttribute("aria-valuetext", "0 of " + totalSlots + " assessment runs processed");
    comparisonProgressLabel.textContent = "Preparing comparison";
    comparisonRunStatus.textContent = "Creating fresh runs for both built-in demos…";
    renderComparisonSummary(slots);

    for (let index = 0; index < settings.runsPerVersion; index += 1) {
      for (const demo of [
        { key: "broken", label: "Broken demo", path: "/demo/broken" },
        { key: "fixed", label: "Fixed demo", path: "/demo/fixed" },
      ]) {
        const runNumber = index + 1;
        comparisonProgressLabel.textContent = demo.label + " · run " + runNumber + " of " + settings.runsPerVersion;
        comparisonRunStatus.textContent = "Creating a fresh " + demo.label.toLowerCase() + " run…";
        let operation = "creation";
        let slot;
        try {
          const createResponse = await fetch("/api/runs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              targetUrl: window.location.origin + demo.path,
              goal: configuration.goal,
              simulationMode: configuration.simulationMode,
            }),
          });
          const created = await readResponseJson(createResponse);
          if (!createResponse.ok) {
            throw new Error(responseError(created, "The run could not be created."));
          }
          if (typeof created.id !== "string" || !created.id) {
            throw new Error("The server did not return a run identifier.");
          }

          operation = "execution";
          setCancelableRun(created.id, "comparison");
          comparisonRunStatus.textContent = "Running " + demo.label.toLowerCase() + " · run " + runNumber + "…";
          const { response, result } = await executeRun(created.id, "comparison");
          if (!response.ok) {
            throw new Error(responseError(result, "The run could not be completed."));
          }
          if (!result || typeof result.id !== "string" || !result.id) {
            throw new Error("The server did not return a completed run record.");
          }
          slot = { record: result };
        } catch (error) {
          if (activeLiveRunId) clearCancelableRun(activeLiveRunId);
          const detail = error instanceof Error && error.message
            ? error.message.replace(/[\r\n\t]+/g, " ").slice(0, 300)
            : "The local run could not be completed.";
          slot = {
            record: null,
            error: (operation === "creation" ? "Creation failed: " : "Execution failed: ") + detail,
          };
        }

        slots[demo.key].push(slot);
        processed += 1;
        comparisonProgress.value = processed;
        comparisonProgressCount.textContent = String(processed);
        comparisonProgress.setAttribute(
          "aria-valuetext",
          processed + " of " + totalSlots + " assessment runs processed",
        );
        renderComparisonSide(demo.key, slots[demo.key], containers[demo.key]);
        renderComparisonSummary(slots);
        comparisonRunStatus.textContent = slot.record
          ? demo.label + " run " + runNumber + " returned with status " + (slot.record.status || "not recorded") + "."
          : demo.label + " run " + runNumber + " failed: " + slot.error;
      }
    }

    comparisonProgressLabel.textContent = "Comparison complete";
    comparisonRunStatus.textContent = "Processed " + processed + " of " + totalSlots + " assessment slots.";
  } catch (error) {
    comparisonProgressLabel.textContent = "Comparison stopped";
    comparisonRunStatus.textContent = error instanceof Error
      ? error.message
      : "The comparison could not continue.";
  } finally {
    if (activeLiveRunId) clearCancelableRun(activeLiveRunId);
    setWorkflowBusy(false);
  }
}

/** renderComparisonSettings shows the exact shared choices used in every create request. */
function renderComparisonSettings(settings) {
  const list = document.querySelector("#comparison-settings");
  const values = [
    ["Targets", settings.targetUrl],
    ["Assessment scope", settings.scope === "whole-site" ? "Whole page" : "Goal focused"],
    ["Goal", settings.goal || "None configured"],
    ["Simulation mode", settings.simulationMode ? "On" : "Off"],
    ["Runs per demo", settings.consistencyLevel + " · " + formatRunCount(settings.runsPerVersion)],
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

/** renderComparisonSide renders only the current slot's returned record or its own safe error. */
function renderComparisonSide(demo, slots, container) {
  const fragment = document.createDocumentFragment();
  for (const [index, slot] of slots.entries()) {
    const article = document.createElement("article");
    article.className = "comparison-slot";
    const heading = document.createElement("h4");
    heading.textContent = "Run " + (index + 1);
    article.append(heading);
    if (slot.record) {
      const reportRoot = document.createElement("div");
      reportRoot.className = "run-report-root comparison-run-report";
      reportRoot.id = "comparison-" + demo + "-run-" + (index + 1);
      renderRunReport(slot.record, reportRoot);
      article.append(reportRoot);
    } else {
      const error = document.createElement("p");
      error.className = "comparison-slot-error";
      error.setAttribute("role", "status");
      error.textContent = slot.error || "This run did not return a record.";
      article.append(error);
    }
    fragment.append(article);
  }
  container.replaceChildren(fragment);
}

/** renderComparisonSummary groups raw facts by demo and keeps missing facts separate. */
function renderComparisonSummary(slots) {
  const sides = [
    ["Broken demo", slots.broken],
    ["Fixed demo", slots.fixed],
  ];
  const statusList = document.querySelector("#comparison-status-counts");
  const coverageList = document.querySelector("#comparison-coverage-counts");
  const successList = document.querySelector("#comparison-success-counts");
  const statusMissing = document.querySelector("#comparison-status-missing");
  const coverageMissing = document.querySelector("#comparison-coverage-missing");
  const executionErrors = document.querySelector("#comparison-error-counts");

  statusList.replaceChildren();
  coverageList.replaceChildren();
  successList.replaceChildren();
  const statusMissingLabels = [];
  const coverageMissingLabels = [];
  const errorLabels = [];

  for (const [label, sideSlots] of sides) {
    const summary = summarizeLiveComparisonCounts(sideSlots);
    appendGroupedCounts(statusList, label, summary.terminalStatuses.map(({ status, count }) => (
      status + ": " + count
    )), summary.missingTerminalStatus ? "Terminal status not recorded: " + summary.missingTerminalStatus : null);
    appendGroupedCounts(coverageList, label, summary.coverageGroups.map((group) => {
      const pair = (group.unit ? group.unit + " · " : "")
        + "observed " + (group.observed === null ? "not recorded" : group.observed)
        + " / expected " + (group.expected === null ? "not recorded" : group.expected);
      return group.status ? pair + " · status " + group.status + ": " + group.count : pair + ": " + group.count;
    }), summary.missingCoverage ? "Coverage not recorded: " + summary.missingCoverage : null);
    appendGroupedCounts(successList, label, [
      "Reached: " + summary.successOutcomes.reached,
      "Not reached: " + summary.successOutcomes.notReached,
      "Not recorded: " + summary.successOutcomes.notRecorded,
      "Not configured: " + summary.successOutcomes.notConfigured,
    ]);
    statusMissingLabels.push(label + ": " + summary.missingTerminalStatus + " missing");
    coverageMissingLabels.push(label + ": " + summary.missingCoverage + " missing");
    errorLabels.push(
      label + ": " + summary.creationFailures + " creation errors · "
        + summary.executionFailures + " execution errors",
    );
  }

  statusMissing.textContent = statusMissingLabels.join(" · ");
  coverageMissing.textContent = coverageMissingLabels.join(" · ");
  executionErrors.textContent = errorLabels.join(" · ");
}

/** appendGroupedCounts adds one labeled group's recorded values and explicit missing-fact rows. */
function appendGroupedCounts(container, label, values, missing) {
  const group = document.createElement("li");
  const heading = document.createElement("strong");
  heading.textContent = label;
  const list = document.createElement("ul");
  for (const value of values) {
    const item = document.createElement("li");
    item.textContent = value;
    list.append(item);
  }
  if (values.length === 0) {
    const item = document.createElement("li");
    item.textContent = "No recorded values";
    list.append(item);
  }
  if (missing) {
    const item = document.createElement("li");
    item.textContent = missing;
    list.append(item);
  }
  group.append(heading, list);
  container.append(group);
}

/** clearTargetValidationError removes stale feedback once the target input changes. */
function clearTargetValidationError() {
  setError(targetInput, targetError, "");
  comparisonSection.hidden = true;
  if (!workflowInProgress) liveAssessmentSection.hidden = true;
}

/** clearStaleViews clears a prior result after assessment settings change. */
function clearStaleViews() {
  comparisonSection.hidden = true;
  if (!workflowInProgress) liveAssessmentSection.hidden = true;
}

/** updateConsistencyPreview keeps the comparison action's promised run count aligned with the selector. */
function updateConsistencyPreview() {
  const level = consistencyInput.value;
  const runsPerVersion = CONSISTENCY_RUN_COUNTS[level];
  comparisonButton.textContent = "Compare demos · " + formatRunCount(runsPerVersion) + " per version";
  clearStaleViews();
}

/** formatRunCount labels the configured count without adding a score or rate. */
function formatRunCount(count) {
  return count + (count === 1 ? " run" : " runs");
}

/** populateConsistencyOptions derives labels and values from the comparison domain contract. */
function populateConsistencyOptions() {
  const fragment = document.createDocumentFragment();
  for (const [level, runsPerVersion] of Object.entries(CONSISTENCY_RUN_COUNTS)) {
    const option = document.createElement("option");
    option.value = level;
    option.textContent = level + " — " + formatRunCount(runsPerVersion);
    option.selected = level === "Low";
    fragment.append(option);
  }
  consistencyInput.replaceChildren(fragment);
}

form.addEventListener("submit", handleAssessmentSubmit);
comparisonButton.addEventListener("click", handleComparisonRequest);
navButtons.setup.addEventListener("click", () => {
  if (workflowInProgress) return;
  setActiveView("setup");
  targetInput.focus({ preventScroll: true });
});
navButtons.comparison.addEventListener("click", handleComparisonRequest);
newAssessmentButton.addEventListener("click", () => {
  setActiveView("setup");
  targetInput.focus({ preventScroll: true });
});
loadLocalHtmlButton.addEventListener("click", handleLocalHtmlUpload);
builtInTargetInput.addEventListener("change", selectBuiltInTarget);
cancelLiveAssessmentButton.addEventListener("click", handleCancelLiveAssessment);
comparisonCancelButton.addEventListener("click", handleCancelLiveAssessment);
targetInput.addEventListener("input", () => {
  updateRecognizedTargetLabel();
  clearTargetValidationError();
});
goalInput.addEventListener("input", updateScopePreview);
simulationInput.addEventListener("change", clearStaleViews);
consistencyInput.addEventListener("change", updateConsistencyPreview);
const defaultTarget = `${window.location.origin}/demo/fixed`;
targetInput.value = defaultTarget;
builtInTargetInput.value = "/demo/fixed";
updateRecognizedTargetLabel();

updateScopePreview();
populateConsistencyOptions();
updateConsistencyPreview();
