import {
  getAssessmentScope,
  validateAssessmentGoal,
  validateTargetUrl,
} from "./assessment.mjs";
import {
  CONSISTENCY_RUN_COUNTS,
  buildSiteComparison,
  formatCount,
  formatTerminalStatus,
} from "./comparison.mjs";
import {
  AGENT_UPDATED_GOAL_FOCUSED_SAMPLE,
  AGENT_UPDATED_WHOLE_SITE_SAMPLE,
  GOAL_FOCUSED_SAMPLE,
  WHOLE_SITE_SAMPLE,
} from "./sample-report.mjs";

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
const comparisonSection = document.querySelector("#sample-comparison");
const comparisonHeading = document.querySelector("#comparison-heading");
const setupSection = document.querySelector("#setup");
const newAssessmentButton = document.querySelector("#new-assessment");
const navButtons = {
  setup: document.querySelector("#nav-setup"),
  comparison: document.querySelector("#nav-comparison"),
};
let liveRecordUrl;
let reportRenderSequence = 0;
let activeLiveRunId = null;

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

const ASSESSMENT_EVIDENCE_PRESENTATION = {
  action: {
    label: "keyboard action",
    shortLabel: "action",
    describeRecord: ({ key, target, result }) => `${key} at ${target}: ${result}`,
    describeChange: (change) => (
      `Keyboard action at ${change.target}: original “${change.original.result}” (${change.original.outcome}), updated “${change.updated.result}” (${change.updated.outcome}).`
    ),
    describeFailure: (record) => record.result,
  },
  focus: {
    label: "focus observation",
    shortLabel: "focus",
    describeRecord: ({ target, role, indicator }) => `${target} (${role}): ${indicator}`,
    describeChange: (change) => (
      `Focus observation at ${change.target}: original “${change.original.indicator}”, updated “${change.updated.indicator}” (${formatEvidenceDirection(change.direction)}).`
    ),
    describeFailure: (record) => record.indicator,
  },
};

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
  if (!activeLiveRunId) setActiveView("setup");
}

/** comparisonEvidenceLink labels a reference to its source report's underlying evidence. */
function comparisonEvidenceLink(version, record, runNumber = 1) {
  const reportName = version === "original" ? "Original" : "Updated";
  return { version, id: record.id, runNumber, label: `${reportName} run ${runNumber} ${record.id}` };
}

/** comparisonEvidencePair links a changed item to both reports with consistent labels. */
function comparisonEvidencePair(original, updated, runNumber = 1) {
  return [
    comparisonEvidenceLink("original", original, runNumber),
    comparisonEvidenceLink("updated", updated, runNumber),
  ];
}

/** validateCurrentConfiguration applies the same target and goal boundary to reports and comparisons. */
function validateCurrentConfiguration() {
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
  liveTerminal.hidden = false;
  liveResult.hidden = true;
  terminalLog.replaceChildren();
  setRunStage(25, "Settings checked", "Local target and assessment settings checked.");
  liveAssessmentStatus.textContent = "Creating a fresh local run…";
  liveRecordDownload.hidden = true;
  liveRecordDetails.hidden = true;
  liveAssessmentButton.disabled = true;
  for (const button of Object.values(navButtons)) button.disabled = true;

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
    const created = await createResponse.json();
    if (!createResponse.ok) {
      throw new Error(created.error?.message || "The run could not be created.");
    }

    setRunStage(50, "Run created", "Local run record created.");
    activeLiveRunId = created.id;
    cancelLiveAssessmentButton.hidden = false;
    cancelLiveAssessmentButton.disabled = false;
    setRunStage(75, "Assessment running", "Isolated keyboard assessment started.");
    liveAssessmentStatus.textContent = "The isolated browser is checking the page…";
    const executeResponse = await fetch(`/api/runs/${encodeURIComponent(created.id)}/execute`, {
      method: "POST",
    });
    const result = await executeResponse.json();
    if (!executeResponse.ok) {
      throw new Error(result.error?.message || "The run could not be completed.");
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
    activeLiveRunId = null;
    cancelLiveAssessmentButton.hidden = true;
    cancelLiveAssessmentButton.disabled = false;
    liveAssessmentButton.disabled = false;
    for (const button of Object.values(navButtons)) button.disabled = false;
  }
}

/** handleCancelLiveAssessment asks the server to cancel the registered planner while execute remains pending. */
async function handleCancelLiveAssessment() {
  const runId = activeLiveRunId;
  if (!runId) return;

  cancelLiveAssessmentButton.disabled = true;
  liveAssessmentStatus.textContent = "Requesting cancellation…";
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error?.message || "The run could not be cancelled.");
    }
    if (activeLiveRunId === runId) {
      liveAssessmentStatus.textContent = "Cancellation requested. Waiting for the run to finish…";
    }
  } catch (error) {
    if (activeLiveRunId === runId) {
      liveAssessmentStatus.textContent = error instanceof Error
        ? error.message
        : "The run could not be cancelled.";
      cancelLiveAssessmentButton.disabled = false;
    }
  }
}

/** getComparisonSettings records the same selected run count and context for both versions. */
function getComparisonSettings(configuration) {
  const consistencyLevel = consistencyInput.value;
  return {
    targetUrl: configuration.targetUrl,
    scope: configuration.scope,
    goal: configuration.goal,
    simulationMode: configuration.simulationMode,
    interactionProfile: "Keyboard only",
    browserConditions: "Same controlled local browser conditions",
    consistencyLevel,
    runsPerVersion: CONSISTENCY_RUN_COUNTS[consistencyLevel],
  };
}

/** createComparisonSamples creates the same number of explicitly labeled sample slots per version. */
function createComparisonSamples(configuration, settings) {
  const samples = configuration.scope === "whole-site"
    ? [WHOLE_SITE_SAMPLE, AGENT_UPDATED_WHOLE_SITE_SAMPLE]
    : [GOAL_FOCUSED_SAMPLE, AGENT_UPDATED_GOAL_FOCUSED_SAMPLE];

  return samples.map((sample, versionIndex) => Array.from(
    { length: settings.runsPerVersion },
    (_, index) => createRepresentativeComparisonRun({
      sample,
      settings,
      goal: configuration.goal,
      version: versionIndex === 0 ? "original" : "updated",
      index,
    }),
  ));
}

/** createRepresentativeComparisonRun keeps incomplete and agent-failed sample states visible. */
function createRepresentativeComparisonRun({ sample, settings, goal, version, index }) {
  const runNumber = index + 1;
  const run = {
    ...sample,
    runId: index === 0 ? sample.runId : `${sample.runId}-RUN-${runNumber}`,
    goal,
    assessmentSettings: settings,
    comparisonRunNumber: runNumber,
    representativeRunNote: index === 0
      ? "Representative sample slot; no browser run has taken place."
      : `Illustrative repeat slot ${runNumber}; this repeats representative sample evidence and is not an independent browser run.`,
  };

  if (index !== 1) return run;
  if (version === "original") {
    return {
      ...run,
      terminalStatus: "INCONCLUSIVE",
      outcomeTitle: "Representative repeat run remained inconclusive",
      explanationTitle: "This repeat slot is inconclusive.",
      explanation: "The representative website-check values remain visible, but this sample slot is inconclusive and cannot support a resolved comparison on its own.",
    };
  }

  return {
    ...run,
    terminalStatus: "AGENT_FAILED",
    outcomeTitle: "Representative repeat run recorded an agent failure",
    explanationTitle: "This repeat slot records an agent failure.",
    explanation: "The representative website-check values remain visible, while the separate agent failure prevents this sample slot from supporting a resolved comparison on its own.",
    agentFailures: [
      ...(run.agentFailures ?? []),
      "Representative agent failure retained for this sample slot.",
    ],
  };
}

/** handleComparisonRequest shows a validated comparison and moves focus to its result heading. */
function handleComparisonRequest() {
  const configuration = validateCurrentConfiguration();
  if (!configuration) return;

  const settings = getComparisonSettings(configuration);
  const [original, updated] = createComparisonSamples(configuration, settings);
  const comparison = buildSiteComparison(original, updated);
  renderComparison(comparison);
  setActiveView("comparison");
  comparisonHeading.focus({ preventScroll: true });
}

/** renderComparison puts score, metric, and coverage changes ahead of its supporting reports. */
function renderComparison(comparison) {
  const status = document.querySelector("#comparison-status");
  status.textContent = comparison.outcome.label;
  status.dataset.outcome = comparison.outcome.status;
  document.querySelector("#comparison-summary").textContent = comparison.outcome.summary;

  document.querySelector("#comparison-original-score").textContent = formatScore(comparison.score.original);
  document.querySelector("#comparison-original-count").textContent = formatScoreCounts(comparison.score.original);
  document.querySelector("#comparison-original-range").textContent = formatScoreRange(comparison.score.original);
  document.querySelector("#comparison-updated-score").textContent = formatScore(comparison.score.updated);
  document.querySelector("#comparison-updated-count").textContent = formatScoreCounts(comparison.score.updated);
  document.querySelector("#comparison-updated-range").textContent = formatScoreRange(comparison.score.updated);
  document.querySelector("#comparison-score-delta").textContent = formatSigned(comparison.score.deltaPercentagePoints);
  document.querySelector("#comparison-original-coverage").textContent = comparison.coverage.original.label;
  document.querySelector("#comparison-updated-coverage").textContent = comparison.coverage.updated.label;
  document.querySelector("#comparison-coverage-delta").textContent = formatCoverageChange(comparison.coverage);

  renderComparisonRunResults(comparison.runs, comparison.runSummaries);
  renderComparisonMetrics(comparison.metrics);
  renderComparisonEvidence(comparison.evidenceByRun);
  renderComparisonSettings(comparison.settings);
  renderComparisonReports(
    document.querySelector("#comparison-original-report-content"),
    comparison.runs.original,
    "original",
  );
  renderComparisonReports(
    document.querySelector("#comparison-updated-report-content"),
    comparison.runs.updated,
    "updated",
  );
}

/** formatScore labels the average and keeps a missing score explicit instead of presenting it as zero. */
function formatScore(score) {
  const value = score.averagePercentage ?? score.percentage;
  return value === null ? "Unavailable" : `${value}%`;
}

/** formatScoreCounts distinguishes pooled check totals from the number of scored runs. */
function formatScoreCounts(score) {
  if (score.passed === null || score.attempted === null) {
    return `${score.scoredRuns} of ${formatCount(score.totalRuns, "run")} scored`;
  }
  return `${score.passed} passed / ${score.attempted} attempted across ${formatCount(score.totalRuns, "run")}`;
}

/** formatScoreRange reports only observed score bounds and names any runs without a score. */
function formatScoreRange(score) {
  const range = score.range
    ? `Range ${score.range.minimum}–${score.range.maximum}%`
    : "Range unavailable";
  return `${range} · ${score.scoredRuns} of ${formatCount(score.totalRuns, "run")} scored${score.unscoredRuns > 0 ? `; ${score.unscoredRuns} without a score` : ""}`;
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
      : metric.original?.totalRuns > 1
        ? `${formatSigned(metric.percentagePointDelta)} pp average`
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
  if (metric?.totalRuns > 1) {
    return metric.scoredRuns === metric.totalRuns
      ? `${metric.averagePercentage}% average (${metric.scoredRuns} runs)`
      : `Unavailable (${metric.scoredRuns} of ${metric.totalRuns} runs recorded)`;
  }
  return metric
    ? `${metric.passed} / ${metric.attempted} (${metric.percentage ?? "—"}%)`
    : "Not recorded";
}

/** renderComparisonRunResults gives every result row status and failure context before report details open. */
function renderComparisonRunResults(runs, summaries) {
  const container = document.querySelector("#comparison-run-results");
  const fragment = document.createDocumentFragment();
  for (const [version, title] of [["original", "Original site"], ["updated", "Agent-updated site"]]) {
    const group = document.createElement("section");
    group.className = "comparison-run-group";
    const heading = document.createElement("h4");
    heading.textContent = title;
    const list = document.createElement("ol");
    for (const [index, run] of runs[version].entries()) {
      const summary = summaries[version][index];
      const item = document.createElement("li");
      const score = summary.score.percentage === null ? "score unavailable" : `${summary.score.percentage}% score`;
      const runHeading = document.createElement("strong");
      runHeading.textContent = `Run ${index + 1} · ${formatTerminalStatus(summary.terminalStatus)}`;
      const details = document.createElement("span");
      details.textContent = `${run.runId}: ${score}; ${summary.coverage ?? "coverage unavailable"}.`;
      item.append(runHeading, document.createTextNode(" — "), details);
      if (summary.agentFailures.length > 0) {
        const failures = document.createElement("span");
        failures.className = "comparison-run-agent-failures";
        failures.textContent = `Agent failures: ${summary.agentFailures.join("; ")}`;
        item.append(failures);
      }
      if (summary.warnings.length > 0) {
        const warnings = document.createElement("span");
        warnings.className = "comparison-run-agent-failures";
        warnings.textContent = `Warnings: ${summary.warnings.join("; ")}`;
        item.append(warnings);
      }
      list.append(item);
    }
    group.append(heading, list);
    fragment.append(group);
  }
  container.replaceChildren(fragment);
}

/** renderComparisonEvidence names every run's differences and links to that run's report. */
function renderComparisonEvidence(evidenceByRun) {
  const list = document.querySelector("#comparison-evidence-changes");
  const fragment = document.createDocumentFragment();
  const addEvidenceItem = (runNumber, text, links = []) => {
    const item = document.createElement("li");
    item.append(document.createTextNode(`Run ${runNumber}: ${text}`));
    for (const { version, id, label, runNumber: linkRunNumber } of links) {
      item.append(document.createTextNode(" "));
      const link = document.createElement("a");
      link.href = `#comparison-${version}-run-${linkRunNumber}-${id}`;
      link.textContent = label;
      link.addEventListener("click", () => {
        document.querySelector(`#comparison-${version}-report`).open = true;
      });
      item.append(link);
    }
    fragment.append(item);
  };

  for (const { runNumber, evidence } of evidenceByRun) {
    const addRunEvidence = (text, links = []) => addEvidenceItem(runNumber, text, links);
    for (const change of evidence.assessmentChanges) {
    const presentation = ASSESSMENT_EVIDENCE_PRESENTATION[change.kind];
    if (change.change !== "changed") {
      const version = change.change === "added" ? "updated" : "original";
      const reportName = version === "updated" ? "Updated" : "Original";
      const record = change.record;
      const addition = record.outcome === "passed"
        ? `a passing ${presentation.label}`
        : `a ${presentation.label} without a recorded outcome`;
      const description = change.change === "added"
        ? `${reportName} report adds ${addition}: ${presentation.describeRecord(record)}.`
        : `Original report has no matching updated ${presentation.label}: ${presentation.describeRecord(record)} (${record.outcome ?? "outcome not recorded"}).`;
      addRunEvidence(description, [comparisonEvidenceLink(version, record, runNumber)]);
      continue;
    }

    addRunEvidence(presentation.describeChange(change), comparisonEvidencePair(change.original, change.updated, runNumber));
    }
    for (const failure of evidence.persistentFailures) {
    const presentation = ASSESSMENT_EVIDENCE_PRESENTATION[failure.kind];
    addRunEvidence(
      `Both reports record a failed ${presentation.shortLabel} check at ${failure.target}.`,
      comparisonEvidencePair(failure.original, failure.updated, runNumber),
    );
    }
    for (const failure of evidence.additionalUpdatedFailures) {
    const presentation = ASSESSMENT_EVIDENCE_PRESENTATION[failure.kind];
    addRunEvidence(
      `Updated report adds a failed ${presentation.label}: ${presentation.describeFailure(failure.record)} at ${failure.target}.`,
      [comparisonEvidenceLink("updated", failure.record, runNumber)],
    );
    }
    for (const failure of evidence.unpairedOriginalFailures) {
    const presentation = ASSESSMENT_EVIDENCE_PRESENTATION[failure.kind];
    addRunEvidence(
      `Original failed ${presentation.shortLabel} evidence at ${failure.target} has no matching updated observation; its outcome is unknown.`,
      [comparisonEvidenceLink("original", failure.record, runNumber)],
    );
    }
    for (const change of evidence.supportingChanges) {
      appendSupportingEvidenceDifference(addRunEvidence, change, runNumber);
    }
    for (const message of evidence.addedAgentFailures) {
      addRunEvidence(`Updated report also records an agent failure: ${message}`);
    }
    for (const warning of evidence.addedWarnings) {
      addRunEvidence(`Updated report adds a warning: ${warning}`);
    }
    for (const message of evidence.resolvedAgentFailures) {
      addRunEvidence(`Original report records an agent failure not present in the updated report: ${message}`);
    }
    for (const warning of evidence.resolvedWarnings) {
      addRunEvidence(`Original report adds a warning not present in the updated report: ${warning}`);
    }
  }

  if (fragment.childNodes.length === 0) {
    const item = document.createElement("li");
    item.textContent = "No action, focus, recovery, screenshot, or citation differences were recorded in any run.";
    fragment.append(item);
  }
  list.replaceChildren(fragment);
}

/** appendSupportingEvidenceDifference gives recovery notes, screenshots, and citations concise linked summaries. */
function appendSupportingEvidenceDifference(addEvidenceItem, change, runNumber) {
  if (change.kind === "recovery") {
    if (change.change === "changed") {
      addEvidenceItem(
        `Recovery evidence ${change.original.id} changed: original “${change.original.text}”, updated “${change.updated.text}”.`,
        comparisonEvidencePair(change.original, change.updated, runNumber),
      );
    } else {
      const version = change.change === "added" ? "updated" : "original";
      const record = change.record;
      addEvidenceItem(
        `${version === "updated" ? "Updated" : "Original"} report ${change.change} recovery evidence ${record.id}: ${record.text}.`,
        [comparisonEvidenceLink(version, record, runNumber)],
      );
    }
    return;
  }

  if (change.kind === "reference") {
    const original = change.original;
    const updated = change.updated;
    const record = change.record;
    const links = change.change === "changed"
      ? comparisonEvidencePair(original, updated, runNumber)
      : [comparisonEvidenceLink(change.change === "added" ? "updated" : "original", record, runNumber)];
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
      comparisonEvidencePair(original, updated, runNumber),
    );
  } else {
    const version = change.change === "added" ? "updated" : "original";
    addEvidenceItem(
      `${version === "updated" ? "Updated" : "Original"} report ${change.change} screenshot mockup ${record.id}: ${describeScreenshot(record)}.`,
      [comparisonEvidenceLink(version, record, runNumber)],
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

/** renderComparisonSettings makes the shared setup and selected run count explicit. */
function renderComparisonSettings(settings) {
  const list = document.querySelector("#comparison-settings");
  const values = [
    ["Target", settings.targetUrl],
    ["Assessment scope", formatScopeLabel(settings.scope)],
    ["Goal", settings.goal ?? "None (whole-site)"],
    ["Simulation mode", settings.simulationMode ? "On" : "Off"],
    ["Interaction profile", settings.interactionProfile],
    ["Browser conditions", settings.browserConditions],
    ["Consistency", `${settings.consistencyLevel} — ${formatCount(settings.runsPerVersion, "assessment")} per version`],
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

/** renderComparisonReports keeps every run's report and evidence available inside its version details. */
function renderComparisonReports(container, samples, version) {
  const fragment = document.createDocumentFragment();
  for (const [index, sample] of samples.entries()) {
    const run = document.createElement("section");
    run.className = "comparison-report-run";
    const heading = document.createElement("h4");
    heading.textContent = `Run ${index + 1} · ${sample.runId}`;
    run.append(heading);
    renderComparisonReport(run, sample, version, index + 1);
    fragment.append(run);
  }
  container.replaceChildren(fragment);
}

/** renderComparisonReport keeps all report facts and evidence available inside one run's details. */
function renderComparisonReport(container, sample, version, runNumber) {
  const fragment = document.createDocumentFragment();
  const idPrefix = `comparison-${version}-run-${runNumber}-`;
  const evidenceIds = getComparisonEvidenceIds(sample, idPrefix);

  appendComparisonHeading(fragment, "Report summary");
  appendComparisonParagraph(fragment, "Run", sample.runId);
  appendComparisonParagraph(fragment, "Sample provenance", sample.representativeRunNote);
  appendComparisonParagraph(fragment, "Terminal state", formatTerminalStatus(sample.terminalStatus));
  appendComparisonParagraph(fragment, "Assessment scope", formatScopeLabel(sample.scope));
  appendComparisonParagraph(fragment, "Target", sample.assessmentSettings.targetUrl);
  appendComparisonParagraph(fragment, "Goal", sample.assessmentSettings.goal ?? "None supplied");
  appendComparisonParagraph(fragment, "Simulation mode", sample.assessmentSettings.simulationMode ? "On" : "Off");
  appendComparisonParagraph(fragment, "Coverage", sample.coverage);
  appendComparisonParagraph(fragment, "Duration", sample.duration);
  appendComparisonParagraph(fragment, "Interaction count", String(sample.interactionCount));
  appendComparisonParagraph(fragment, "Score", formatReportScore(sample.score));
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

  container.append(fragment);
}

/** formatReportScore never turns an unavailable score into a misleading null percentage. */
function formatReportScore(score) {
  if (!score || score.percentage === null) return score?.label ?? "Score unavailable";
  return `${score.label} (${score.percentage}%)`;
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

/** appendComparisonHeading nests report sections below their visible run heading. */
function appendComparisonHeading(parent, text) {
  const heading = document.createElement("h5");
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

/** clearTargetValidationError removes stale feedback once the target input changes. */
function clearTargetValidationError() {
  setError(targetInput, targetError, "");
  comparisonSection.hidden = true;
  if (!activeLiveRunId) liveAssessmentSection.hidden = true;
}

/** clearStaleViews clears a prior result after assessment settings change. */
function clearStaleViews() {
  comparisonSection.hidden = true;
  if (!activeLiveRunId) liveAssessmentSection.hidden = true;
}

/** updateConsistencyPreview keeps the comparison action's promised run count aligned with the selector. */
function updateConsistencyPreview() {
  const level = consistencyInput.value;
  const runsPerVersion = CONSISTENCY_RUN_COUNTS[level];
  comparisonButton.textContent = `Compare demos · ${formatCount(runsPerVersion, "run")} per version`;
  clearStaleViews();
}

/** populateConsistencyOptions derives labels and values from the comparison domain contract. */
function populateConsistencyOptions() {
  const fragment = document.createDocumentFragment();
  for (const [level, runsPerVersion] of Object.entries(CONSISTENCY_RUN_COUNTS)) {
    const option = document.createElement("option");
    option.value = level;
    option.textContent = `${level} — ${formatCount(runsPerVersion, "assessment")} per version`;
    option.selected = level === "Low";
    fragment.append(option);
  }
  consistencyInput.replaceChildren(fragment);
}

form.addEventListener("submit", handleAssessmentSubmit);
comparisonButton.addEventListener("click", handleComparisonRequest);
navButtons.setup.addEventListener("click", () => {
  if (activeLiveRunId) return;
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
