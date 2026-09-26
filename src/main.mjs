import {
  getAssessmentScope,
  validateAssessmentGoal,
  validateTargetUrl,
} from "./assessment.mjs";
import { filterSensitiveSiteFiles } from "./site-files.mjs";

const form = document.querySelector("#assessment-form");
const targetInput = document.querySelector("#target-url");
const pageOnlyInput = document.querySelector("#page-only");
const sitePageLimitInput = document.querySelector("#site-page-limit");
const sitePageLimitError = document.querySelector("#site-page-limit-error");
const targetSiteFilesInput = document.querySelector("#target-site-files");
const chooseLocalFilesButton = document.querySelector("#choose-local-files");
const targetSiteStatus = document.querySelector("#target-site-status");
const recognizedTarget = document.querySelector("#recognized-target");
const goalInput = document.querySelector("#assessment-goal");
const simulationInput = document.querySelector("#simulation-mode");
const cancelLiveAssessmentButton = document.querySelector("#cancel-live-assessment");
const liveAssessmentSection = document.querySelector("#live-assessment");
const liveAssessmentStatus = document.querySelector("#live-assessment-status");
const liveRecordDownload = document.querySelector("#download-live-record");
const liveRecordDetails = document.querySelector("#live-record-details");
const liveRecordJson = document.querySelector("#live-record-json");
const liveTerminal = document.querySelector("#live-terminal");
const liveResult = document.querySelector("#live-result");
const liveRunReport = document.querySelector("#live-run-report");
const reportEmptyState = document.querySelector("#report-empty-state");
const reportEmptyNewAssessmentButton = document.querySelector("#report-empty-new-assessment");
const runReportTemplate = document.querySelector("#run-report-template");
const liveRunProgress = document.querySelector("#live-run-progress");
const liveProgressLabel = document.querySelector("#live-progress-label");
const liveProgressPercent = document.querySelector("#live-progress-percent");
const terminalLog = document.querySelector("#terminal-log");
const targetError = document.querySelector("#target-error");
const goalError = document.querySelector("#goal-error");
const scopeStatus = document.querySelector("#scope-status");
const submitLabel = document.querySelector("#submit-label");
const setupSection = document.querySelector("#setup");
const newAssessmentButton = document.querySelector("#new-assessment");
const navButtons = {
  setup: document.querySelector("#nav-setup"),
  report: document.querySelector("#nav-report"),
};
let liveRecordUrl;
let reportRenderSequence = 0;
let activeLiveRunId = null;
let workflowInProgress = false;
let latestRunRecord = null;

/** positionHelpTooltip keeps each help popup inside the visible browser window. */
function positionHelpTooltip(button) {
  const tooltipId = button.getAttribute("aria-describedby");
  const tooltip = button.helpTooltip ?? (tooltipId ? document.getElementById(tooltipId) : null);
  if (!tooltip) return;
  button.helpTooltip = tooltip;
  if (button.closest(".report-label-with-help")) tooltip.classList.add("tooltip-report-label");
  if (button.closest(".report-progress-heading")) tooltip.classList.add("tooltip-report-progress");
  if (tooltip.parentElement !== document.body) document.body.append(tooltip);
  tooltip.classList.remove("tooltip-below");
  tooltip.style.display = "block";
  const anchor = button.getBoundingClientRect();
  const bounds = window.visualViewport;
  const viewportWidth = bounds?.width ?? window.innerWidth;
  const viewportHeight = bounds?.height ?? window.innerHeight;
  const offsetLeft = bounds?.offsetLeft ?? 0;
  const offsetTop = bounds?.offsetTop ?? 0;
  const margin = 12;
  const gap = 9;
  const popup = tooltip.getBoundingClientRect();
  const left = Math.max(offsetLeft + margin, Math.min(
    anchor.left + anchor.width / 2 - popup.width / 2,
    offsetLeft + viewportWidth - popup.width - margin,
  ));
  const aboveTop = anchor.top - popup.height - gap;
  const belowTop = anchor.bottom + gap;
  const aboveSpace = anchor.top - offsetTop;
  const belowSpace = offsetTop + viewportHeight - anchor.bottom;
  let top = aboveTop;
  if (aboveTop < offsetTop + margin && belowSpace > aboveSpace) {
    top = belowTop;
    tooltip.classList.add("tooltip-below");
  }
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${Math.max(offsetTop + margin, Math.min(top, offsetTop + viewportHeight - popup.height - margin))}px`;
  tooltip.style.setProperty("--tooltip-arrow-x", `${Math.max(10, Math.min(popup.width - 10, anchor.left + anchor.width / 2 - left))}px`);
}

function closeHelpTooltip(button) {
  const tooltipId = button.getAttribute("aria-describedby");
  const tooltip = tooltipId ? document.getElementById(tooltipId) : null;
  if (tooltip) tooltip.style.display = "none";
}

document.addEventListener("pointerover", (event) => {
  const button = event.target.closest?.(".help-icon");
  if (button) positionHelpTooltip(button);
});
document.addEventListener("pointerout", (event) => {
  const button = event.target.closest?.(".help-icon");
  if (!button || button.contains(event.relatedTarget) || button.matches(":focus-visible")) return;
  if (event.relatedTarget === button.helpTooltip || button.helpTooltip?.contains(event.relatedTarget)) return;
  closeHelpTooltip(button);
});
document.addEventListener("focusin", (event) => {
  const button = event.target.closest?.(".help-icon");
  if (button) positionHelpTooltip(button);
});
document.addEventListener("focusout", (event) => {
  const button = event.target.closest?.(".help-icon");
  if (button) closeHelpTooltip(button);
});
function repositionOpenHelpTooltips() {
  for (const button of document.querySelectorAll(".help-icon:hover, .help-icon:focus-visible")) positionHelpTooltip(button);
}
window.addEventListener("resize", repositionOpenHelpTooltips);
window.addEventListener("scroll", repositionOpenHelpTooltips, true);
window.visualViewport?.addEventListener("resize", repositionOpenHelpTooltips);
window.visualViewport?.addEventListener("scroll", repositionOpenHelpTooltips);

const MAX_TARGET_SITE_FILES = 200;
const MAX_TARGET_SITE_TOTAL_BYTES = 20 * 1024 * 1024;
const MAX_TARGET_SITE_FILE_BYTES = 5 * 1024 * 1024;
/** setActiveView keeps one focused app screen visible without scrolling the document. */
function setActiveView(view) {
  const activeView = view === "live" ? "report" : view;
  setupSection.hidden = activeView !== "setup";
  liveAssessmentSection.hidden = activeView !== "report";
  for (const [key, button] of Object.entries(navButtons)) {
    if (key === activeView) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
}

/** showReportView displays the latest real run or explains how to create the first report. */
function showReportView() {
  if (workflowInProgress) return;
  setActiveView("report");
  liveTerminal.hidden = true;
  liveResult.hidden = !latestRunRecord;
  reportEmptyState.hidden = Boolean(latestRunRecord);
}

/** loadLatestRunReport restores the latest saved real run after a page reload. */
async function loadLatestRunReport() {
  try {
    const response = await fetch("/api/runs/latest");
    if (!response.ok) return;
    const record = await response.json();
    if (!record || typeof record.id !== "string" || !record.id) return;
    latestRunRecord = record;
    renderRunReport(record, liveRunReport);
    const serialized = JSON.stringify(record, null, 2);
    liveRecordJson.textContent = serialized;
    if (liveRecordUrl) URL.revokeObjectURL(liveRecordUrl);
    liveRecordUrl = URL.createObjectURL(new Blob([serialized], { type: "application/json" }));
    liveRecordDownload.href = liveRecordUrl;
    liveRecordDownload.download = `access-trace-${record.id}.json`;
    liveRecordDownload.hidden = false;
    liveRecordDetails.hidden = false;
    reportEmptyState.hidden = true;
  } catch {
    // The report's empty state remains available if no local run can be loaded.
  }
}

/** loadSitePageLimitDefault reflects the developer's default unless the user edits the field first. */
async function loadSitePageLimitDefault() {
  try {
    const response = await fetch("/api/config");
    if (!response.ok) return;
    const configuration = await response.json();
    const value = configuration?.defaultSitePageLimit;
    if (!sitePageLimitInput.dataset.userEdited && Number.isSafeInteger(value) && value >= 0 && value <= 500) {
      sitePageLimitInput.value = String(value);
    }
  } catch {
    // The HTML default remains available if local configuration cannot load.
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
function setCancelableRun(runId) {
  activeLiveRunId = runId;
  cancelLiveAssessmentButton.hidden = !runId;
  cancelLiveAssessmentButton.disabled = false;
}

/** clearCancelableRun removes the stop target as soon as the stored journey reaches a terminal state. */
function clearCancelableRun(runId) {
  if (activeLiveRunId !== runId) return;
  setCancelableRun(null);
}

/** waitForRunTerminal watches durable run status while execute remains open for the evidence review. */
async function waitForRunTerminal(runId, shouldContinue, onTerminal) {
  let activityCount = 0;
  while (shouldContinue()) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1500);
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`, {
        signal: controller.signal,
      });
      if (response.ok) {
        const record = await response.json();
        if (record && typeof record.status === "string") {
          const activityResponse = await fetch(
            `/api/runs/${encodeURIComponent(runId)}/activity`,
            { signal: controller.signal },
          );
          if (activityResponse.ok) {
            const activity = await activityResponse.json();
            const events = Array.isArray(activity.events) ? activity.events : [];
            for (const event of events.slice(activityCount)) {
              appendTerminalActivity(event.message);
              liveAssessmentStatus.textContent = event.message;
            }
            activityCount = events.length;
          }
        }
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
async function executeRun(runId) {
  let requestSettled = false;
  const monitor = waitForRunTerminal(runId, () => !requestSettled, () => {
    clearCancelableRun(runId);
    liveAssessmentStatus.textContent = "Browser run finished. Evidence review is running…";
    setRunStage(90, "Reviewing evidence", "Browser run saved; preparing its evidence review.");
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

/** readResponseJson tolerates a non-JSON server failure while keeping a useful fallback. */
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

/** appendTerminalActivity adds one safe, timestamped line to the live run log. */
function appendTerminalActivity(message) {
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
  entry.scrollIntoView({ block: "nearest" });
}

/** setError keeps the visible message and the field's programmatic invalid state aligned. */
function setError(input, container, message) {
  container.textContent = message;
  container.hidden = message === "";
  input.setAttribute("aria-invalid", String(message !== ""));
}

/** clearTargetValidationError removes stale target feedback after its value changes. */
function clearTargetValidationError() {
  setError(targetInput, targetError, "");
  if (!workflowInProgress) liveAssessmentSection.hidden = true;
}

/** clearStaleViews hides the prior report after assessment settings change. */
function clearStaleViews() {
  if (!workflowInProgress) liveAssessmentSection.hidden = true;
}

/** updateScopePreview reflects the optional goal as an explicit whole-site or goal-focused choice. */
function updateScopePreview() {
  const scope = getAssessmentScope(goalInput.value);
  const isWholeSite = scope === "whole-site";
  const label = isWholeSite ? (pageOnlyInput.checked ? "Selected page only" : "Whole site") : "Goal focused";
  scopeStatus.textContent = label;
  submitLabel.textContent = "Start assessment";
  setError(goalInput, goalError, "");
  if (!workflowInProgress) setActiveView("setup");
}

/** validateCurrentConfiguration checks the target and goal before a live assessment. */
function validateCurrentConfiguration() {
  if (workflowInProgress) return null;
  setError(targetInput, targetError, "");
  setError(goalInput, goalError, "");
  setError(sitePageLimitInput, sitePageLimitError, "");

  const validation = validateTargetUrl(targetInput.value, window.location.origin);
  if (!validation.valid) {
    setError(targetInput, targetError, validation.message);
    targetInput.focus();
    return null;
  }

  const sitePageLimit = sitePageLimitInput.valueAsNumber;
  if (!Number.isSafeInteger(sitePageLimit) || sitePageLimit < 0 || sitePageLimit > 500) {
    setError(sitePageLimitInput, sitePageLimitError, "Enter a whole number from 0 to 500.");
    sitePageLimitInput.focus();
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
    pageOnly: pageOnlyInput.checked,
    sitePageLimit,
    simulationMode: simulationInput.checked,
  };
}

/** handleAssessmentSubmit starts the configured live assessment. */
function handleAssessmentSubmit(event) {
  event.preventDefault();
  void handleLiveAssessment();
}

/** updateRecognizedTargetLabel mirrors the active page URL without retaining stale text. */
function updateRecognizedTargetLabel() {
  const validation = validateTargetUrl(targetInput.value, window.location.origin);
  recognizedTarget.textContent = validation.valid
    ? validation.normalizedUrl
    : "No page URL selected";
}

/** uploadLocalPage makes chosen HTML and its relative assets available at an isolated local URL. */
async function uploadLocalPage(input) {
  const selected = [...(input.files ?? [])];
  if (!selected.length) return;

  targetSiteStatus.textContent = "Preparing local page files…";
  const selectedEntries = selected.map((file) => ({ file, path: file.name }));
  const { entries, skippedCount } = filterSensitiveSiteFiles(selectedEntries);
  if (!entries.length) {
    targetSiteStatus.textContent = "No page files remain after excluding likely credentials and private keys.";
    return;
  }
  if (entries.length > MAX_TARGET_SITE_FILES) {
    targetSiteStatus.textContent = `Choose no more than ${MAX_TARGET_SITE_FILES} page files.`;
    return;
  }
  if (entries.some(({ path, file }) => !path || path.startsWith("/") || path.includes("\\") || path.split("/").some((part) => !part || part === "." || part === "..") || file.size > MAX_TARGET_SITE_FILE_BYTES)) {
    targetSiteStatus.textContent = "Page files must use safe relative paths, and each file must be 5 MiB or smaller.";
    return;
  }
  const totalBytes = entries.reduce((sum, entry) => sum + entry.file.size, 0);
  if (totalBytes > MAX_TARGET_SITE_TOTAL_BYTES) {
    targetSiteStatus.textContent = "Selected page files must total 20 MiB or less.";
    return;
  }
  const htmlEntries = entries
    .filter(({ path }) => /\.html?$/i.test(path))
    .sort((left, right) => left.path.localeCompare(right.path));
  const entrypoint = htmlEntries.find(({ path }) => path.toLowerCase() === "index.html")
    || htmlEntries[0];
  if (!entrypoint) {
    targetSiteStatus.textContent = "Choose an HTML file together with any supporting assets.";
    return;
  }

  const body = new FormData();
  body.append("entrypoint", entrypoint.path);
  for (const { file, path } of entries) body.append("files", file, path);
  targetSiteStatus.textContent = `Uploading ${entries.length} page files…`;
  try {
    const response = await fetch("/api/sites", { method: "POST", body });
    const result = await response.json();
    if (!response.ok) throw new Error(result?.error?.message || "Page files could not be uploaded.");
    targetInput.value = result.targetUrl;
    updateRecognizedTargetLabel();
    clearTargetValidationError();
    clearStaleViews();
    targetSiteStatus.textContent = skippedCount
      ? `Local page ready: ${result.entrypoint} (${entries.length} files uploaded). ${skippedCount} likely credential or private-key files excluded.`
      : `Local page ready: ${result.entrypoint} (${entries.length} files uploaded).`;
    input.value = "";
  } catch (error) {
    targetSiteStatus.textContent = error instanceof Error
      ? error.message
      : "Page files could not be uploaded.";
  }
}

/** setField writes plain text into one report instance without relying on document-wide IDs. */
function setField(report, field, value) {
  const element = report.querySelector(`[data-field="${field}"]`);
  if (element) element.textContent = value;
}

/** setReportProgressBar renders a percentage only when its recorded denominator is meaningful. */
function setReportProgressBar(report, field, observed, expected) {
  const row = report.querySelector(`[data-field="${field}-progress-row"]`);
  if (!row) return;
  const available = observed !== null && expected !== null && expected > 0;
  row.hidden = !available;
  if (!available) return;

  const percentage = Math.round(Math.min(100, (observed / expected) * 100));
  setField(report, `${field}-percent`, `${percentage}%`);
  setField(report, `${field}-count`, `${observed} / ${expected}`);
  const progress = row.querySelector("progress");
  progress.value = percentage;
  progress.setAttribute("aria-valuetext", `${percentage}% (${observed} of ${expected})`);
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

/** appendEvidenceReferenceLinks links review citations to records in this report. */
function appendEvidenceReferenceLinks(list, references, anchors) {
  const items = document.createDocumentFragment();
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
    items.append(item);
  }
  list.replaceChildren(items);
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
  const coverage = stats.coverage ?? stopping.coverage ?? evidence.progress?.coverage;
  const assessmentScope = assessment.assessmentScope ?? record?.assessmentScope;
  const controlsObserved = recordedNumber(coverage?.controlsObserved);
  const controlsExpected = recordedNumber(coverage?.controlsExpected);
  const coverageObserved = recordedNumber(coverage?.controlsObserved ?? coverage?.areasObserved);
  const coverageExpected = recordedNumber(coverage?.controlsExpected ?? coverage?.areasExpected);
  const coverageScore = recordedNumber(coverage?.scorePercentage)
    ?? (coverageObserved !== null && coverageExpected !== null && coverageExpected > 0
      ? Math.round((coverageObserved / coverageExpected) * 100)
      : null);
  const hasPartialScore = assessmentScope === "whole-site"
    && coverageScore !== null
    && coverageScore < 100;
  const statusLabel = status === "COMPLETED" && hasPartialScore
    ? "Completed · partial coverage"
    : formatRunStatus(status);
  const reportToken = `${root.id || "run-report"}-${++reportRenderSequence}`;
  const anchors = new Map();

  setField(report, "heading", typeof record?.id === "string" && record.id
    ? `Run ${record.id}`
    : "Assessment result");
  setField(report, "status-label", statusLabel);
  report.querySelector('[data-field="status"]').dataset.outcome = (
    typeof status === "string" ? status.toLowerCase() : "unknown"
  );

  const interactions = recordedNumber(stats.interactionCount ?? record?.interactionCount);
  setField(report, "interactions", interactions === null ? "—" : `${interactions}`);

  const displayCoverageScore = coverageScore === null
    ? null
    : Math.round(Math.min(100, coverageScore));
  const showCoverageScore = displayCoverageScore !== null;
  const coveragePie = report.querySelector('[data-field="coverage-pie"]');
  coveragePie.style.setProperty("--coverage", `${displayCoverageScore ?? 0}%`);
  coveragePie.setAttribute("aria-label", showCoverageScore
    ? `Overall coverage score: ${displayCoverageScore} percent. The score measures detected controls observed.`
    : "Overall coverage score unavailable for this run.");
  setField(report, "coverage-pie-value", showCoverageScore ? `${displayCoverageScore}%` : "—");
  setReportProgressBar(report, "controls", controlsObserved, controlsExpected);
  setReportProgressBar(
    report,
    "pages",
    recordedNumber(coverage?.areasObserved),
    recordedNumber(coverage?.areasExpected),
  );

  const goalProgress = stats.goalProgress ?? stopping.goalProgress ?? evidence.progress?.goal;
  const completedFields = recordedNumber(goalProgress?.completedFields);
  const expectedFields = recordedNumber(goalProgress?.expectedFields);
  setReportProgressBar(report, "goal", completedFields, expectedFields);

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
  const explanation = report.querySelector('[data-field="review-explanation"]');
  explanation.hidden = !availableReview;
  explanation.textContent = availableReview ? reporting.explanation : "";
  const conditionsList = report.querySelector('[data-field="conditions"]');
  const conditionItems = document.createDocumentFragment();
  const conditions = availableReview && Array.isArray(reporting.conditions)
    ? reporting.conditions
    : [];
  for (const condition of conditions) {
    if (typeof condition?.condition !== "string") continue;
    const item = document.createElement("li");
    const description = document.createElement("p");
    description.className = "report-condition-description";
    description.textContent = condition.condition;
    const mapping = document.createElement("p");
    mapping.className = "report-condition-mapping";
    const criterion = condition.wcagCriterion;
    const source = condition.sourceReference;
    if (condition.mappingStatus === "mapped"
      && typeof criterion?.id === "string"
      && typeof criterion?.name === "string"
      && typeof criterion?.url === "string"
      && criterion.url.startsWith("https://www.w3.org/TR/WCAG22/#")) {
      const link = document.createElement("a");
      link.href = criterion.url;
      link.textContent = `WCAG 2.2 — ${criterion.id} ${criterion.name}`;
      mapping.append(link);
    } else if (condition.mappingStatus === "source"
      && typeof source?.source === "string"
      && typeof source?.sourceType === "string"
      && typeof source?.locator === "string"
      && typeof source?.summary === "string"
      && typeof source?.url === "string"
      && /^https:\/\/(?:iris\.who\.int|www\.etsi\.org|doi\.org)\//.test(source.url)) {
      const link = document.createElement("a");
      link.href = source.url;
      link.textContent = `${source.sourceType}: ${source.source} — ${source.locator}`;
      mapping.append("No direct WCAG match identified. Related source: ", link, `. ${source.summary}`);
    } else {
      mapping.textContent = "No direct WCAG or supplied-source mapping identified.";
    }
    const citations = document.createElement("ul");
    citations.className = "evidence-reference-list";
    citations.setAttribute("aria-label", "Evidence for this condition");
    appendEvidenceReferenceLinks(citations, Array.isArray(condition.evidenceReferences)
      ? condition.evidenceReferences : [], anchors);
    citations.hidden = citations.childElementCount === 0;
    item.append(description, mapping, citations);
    conditionItems.append(item);
  }
  conditionsList.replaceChildren(conditionItems);
  conditionsList.hidden = conditionsList.childElementCount === 0;

  const fixBlock = report.querySelector('[data-field="fix-block"]');
  const proposedFix = typeof reporting.proposedFix === "string" ? reporting.proposedFix.trim() : "";
  fixBlock.hidden = !availableReview || !proposedFix;
  if (!fixBlock.hidden) setField(report, "fix", proposedFix);

  const referencesList = report.querySelector('[data-field="review-references"]');
  const references = availableReview && Array.isArray(reporting.evidenceReferences)
    ? reporting.evidenceReferences
    : [];
  appendEvidenceReferenceLinks(referencesList, references, anchors);
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
  setRunStage(25, "Settings checked", "Page URL and assessment settings checked.");
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
        pageOnly: configuration.pageOnly,
        sitePageLimit: configuration.sitePageLimit,
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
    setCancelableRun(created.id);
    setRunStage(75, "Assessment running", "Isolated keyboard assessment started.");
    liveAssessmentStatus.textContent = "The isolated browser is checking the page…";
    const { response: executeResponse, result: executeResult } = await executeRun(created.id);
    let result = executeResult;
    if (!executeResponse.ok) {
      throw new Error(responseError(result, "The run could not be completed."));
    }
    if (!result || typeof result.id !== "string" || !result.id) {
      throw new Error("The server did not return a completed run record.");
    }

    setRunStage(100, "Result saved", `Run saved with status ${result.status}.`);
    liveAssessmentStatus.textContent = `Run ${result.id} finished: ${result.status}.`;
    latestRunRecord = result;
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
    reportEmptyState.hidden = true;
    setActiveView("report");
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

  const button = cancelLiveAssessmentButton;
  button.disabled = true;
  setRunStatus("Requesting cancellation…");
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
    });
    const result = await readResponseJson(response);
    if (!response.ok) {
      throw new Error(responseError(result, "The run could not be cancelled."));
    }
    if (activeLiveRunId === runId) {
      setRunStatus("Cancellation requested. Waiting for the browser run to finish…");
    }
  } catch (error) {
    if (activeLiveRunId === runId) {
      setRunStatus(error instanceof Error ? error.message : "The run could not be cancelled.");
      button.disabled = false;
    }
  }
}

/** setRunStatus reports cancellation progress to the active assessment. */
function setRunStatus(message) {
  liveAssessmentStatus.textContent = message;
}

form.addEventListener("submit", handleAssessmentSubmit);
navButtons.setup.addEventListener("click", () => {
  if (workflowInProgress) return;
  setActiveView("setup");
  targetInput.focus({ preventScroll: true });
});
navButtons.report.addEventListener("click", showReportView);
newAssessmentButton.addEventListener("click", () => {
  setActiveView("setup");
  targetInput.focus({ preventScroll: true });
});
reportEmptyNewAssessmentButton.addEventListener("click", () => {
  setActiveView("setup");
  targetInput.focus({ preventScroll: true });
});
chooseLocalFilesButton.addEventListener("click", () => {
  targetSiteFilesInput.click();
});
targetSiteFilesInput.addEventListener("change", () => void uploadLocalPage(targetSiteFilesInput));
cancelLiveAssessmentButton.addEventListener("click", handleCancelLiveAssessment);
targetInput.addEventListener("input", () => {
  updateRecognizedTargetLabel();
  clearTargetValidationError();
  targetSiteStatus.textContent = "Using the page URL above.";
});
goalInput.addEventListener("input", updateScopePreview);
pageOnlyInput.addEventListener("change", updateScopePreview);
sitePageLimitInput.addEventListener("input", () => {
  sitePageLimitInput.dataset.userEdited = "true";
  setError(sitePageLimitInput, sitePageLimitError, "");
});
targetInput.value = "";
updateRecognizedTargetLabel();

updateScopePreview();
void loadLatestRunReport();
void loadSitePageLimitDefault();
