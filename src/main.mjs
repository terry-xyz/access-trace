import {
  getAssessmentScope,
  validateAssessmentGoal,
  validateTargetUrl,
} from "./assessment.mjs";
import { filterSensitiveSiteFiles } from "./site-files.mjs";
import { isSensitiveSourcePath } from "./source-context.mjs";
import { canApproveSourceReview, getSourceReviewActions, hasPersistedSourceBaseline, isSafeSourcePath, validateApplicableFiles } from "./source-apply.mjs";

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
const sourceContextFilesInput = document.querySelector("#source-context-files");
const sourceContextDirectoryInput = document.querySelector("#source-context-directory");
const sourceContextStatus = document.querySelector("#source-context-status");
const sourceReviewResult = document.querySelector("#source-review-result");
const sourceReviewStatus = document.querySelector("#source-review-status");
const sourceReviewSummary = document.querySelector("#source-review-summary");
const sourceReviewRootCauseBlock = document.querySelector("#source-review-root-cause-block");
const sourceReviewRootCause = document.querySelector("#source-review-root-cause");
const sourceReviewProposedFixBlock = document.querySelector("#source-review-proposed-fix-block");
const sourceReviewProposedFix = document.querySelector("#source-review-proposed-fix");
const sourceReviewRelevantBlock = document.querySelector("#source-review-relevant-block");
const sourceReviewRelevantPaths = document.querySelector("#source-review-relevant-paths");
const sourceReviewFilesLabel = document.querySelector("#source-review-files-label");
const sourceReviewPatchBlock = document.querySelector("#source-review-patch-block");
const sourceReviewPatch = document.querySelector("#source-review-patch");
const sourceReviewFixButton = document.querySelector("#source-review-fix");
const sourceReviewApproveButton = document.querySelector("#source-review-approve");
const sourceReviewActionStatus = document.querySelector("#source-review-action-status");
const sourcePatchDownload = document.querySelector("#download-source-patch");
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
let sourcePatchUrl;
let selectedSourceFiles = [];
let latestSourceSelection = [];
let uploadedLocalSourceFiles = [];
let reviewedSourceFiles = [];
let sourceReviewBusy = false;
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
const MAX_SOURCE_CONTEXT_FILE_BYTES = 512 * 1024;
const MAX_SOURCE_CONTEXT_REQUEST_BYTES = 5 * 1024 * 1024;
const MAX_SOURCE_CONTEXT_FILES = 200;
const SOURCE_CONTEXT_GENERATED_DIRECTORIES = new Set([
  ".git", ".hg", ".svn", ".next", ".nuxt", ".venv", ".pytest_cache",
  ".mypy_cache", ".ruff_cache", ".cache", "__pycache__", "bower_components",
  "build", "coverage", "dist", "node_modules", "out", "Pods", "site-packages",
  "target", "venv", "vendor",
]);
const SOURCE_CONTEXT_BINARY_EXTENSIONS = new Set([
  ".7z", ".aac", ".avi", ".bin", ".bmp", ".class", ".dll", ".dylib",
  ".eot", ".exe", ".flac", ".gif", ".gz", ".ico", ".jpeg", ".jpg",
  ".mp3", ".mp4", ".otf", ".pdf", ".png", ".so", ".sqlite", ".tar",
  ".ttf", ".wav", ".webm", ".webp", ".woff", ".woff2", ".zip",
]);
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
    renderSourceReview(record, null);
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
    appendTerminalEntry(message);
  }
}

/** appendTerminalEntry adds a safe log line and follows new output only when already at the bottom. */
function appendTerminalEntry(message) {
  const followsOutput = terminalLog.scrollHeight - terminalLog.scrollTop - terminalLog.clientHeight < 24;
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
  if (followsOutput) terminalLog.scrollTop = terminalLog.scrollHeight;
}

/** appendTerminalActivity adds one safe, timestamped line to the live run log. */
function appendTerminalActivity(message) {
  appendTerminalEntry(message);
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

function collectSourceSelection() {
  const entries = [...(sourceContextFilesInput.files ?? [])].map((file) => ({ file, path: file.name, selectionType: "file" }));
  for (const file of sourceContextDirectoryInput.files ?? []) {
    const relative = file.webkitRelativePath || file.name;
    entries.push({ file, path: relative.includes("/") ? relative.slice(relative.indexOf("/") + 1) : relative, selectionType: "directory" });
  }
  return entries;
}

function sourceSkipReason(entry) {
  const parts = entry.path.split("/");
  if (!entry.path || entry.path.startsWith("/") || entry.path.includes("\\") || entry.path.includes("\0") || parts.some((part) => !part || part === "." || part === "..")) return "unsafe-path";
  if (parts.slice(0, -1).some((part) => SOURCE_CONTEXT_GENERATED_DIRECTORIES.has(part))) return "generated-directory";
  if (isSensitiveSourcePath(entry.path)) return "sensitive-file";
  if (entry.file.size > MAX_SOURCE_CONTEXT_FILE_BYTES) return "file-size-limit";
  const name = parts.at(-1).toLowerCase();
  const extension = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
  if (SOURCE_CONTEXT_BINARY_EXTENSIONS.has(extension)) return "binary-content";
  return null;
}

function analyzeSourceSelection(entries) {
  const skipped = [];
  const candidates = [];
  const seen = new Set();
  const sorted = [...entries].sort((a, b) => a.path.localeCompare(b.path));
  for (const entry of sorted) {
    const reason = sourceSkipReason(entry);
    if (reason) { skipped.push({ path: entry.path, reason }); continue; }
    if (seen.has(entry.path)) { skipped.push({ path: entry.path, reason: "duplicate-path" }); continue; }
    seen.add(entry.path);
    candidates.push(entry);
  }
  for (const entry of candidates.slice(MAX_SOURCE_CONTEXT_FILES)) skipped.push({ path: entry.path, reason: "file-count-limit" });
  return { selectedCount: entries.length, candidates: candidates.slice(0, MAX_SOURCE_CONTEXT_FILES), skipped };
}

function updateSourceContextSelection() {
  const explicit = collectSourceSelection();
  selectedSourceFiles = explicit.length ? explicit : uploadedLocalSourceFiles;
  const selection = analyzeSourceSelection(selectedSourceFiles);
  sourceContextStatus.textContent = selection.selectedCount
    ? `${selection.selectedCount} file${selection.selectedCount === 1 ? "" : "s"} selected.`
    : "No files selected.";
  if (latestRunRecord) {
    latestSourceSelection = ["BLOCKED", "COMPLETED", "INCONCLUSIVE"].includes(String(latestRunRecord.status).toUpperCase()) ? selection.candidates : [];
    renderSourceReview(latestRunRecord, latestSourceSelection.length ? selection : null);
  }
}

async function prepareSourceContext(entries) {
  const selection = analyzeSourceSelection(entries);
  const files = [];
  const skipped = [...selection.skipped];
  const encoder = new TextEncoder();
  let requestBytes = encoder.encode('{"sourceContext":{"files":[]}}').byteLength;
  let readCount = 0;
  for (const entry of selection.candidates) {
    let content;
    try {
      const bytes = await entry.file.arrayBuffer();
      readCount += 1;
      content = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      skipped.push({ path: entry.path, reason: "unsupported-text" });
      continue;
    }
    if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/u.test(content)) {
      skipped.push({ path: entry.path, reason: "binary-content" });
      continue;
    }
    const candidate = { path: entry.path, content };
    const size = encoder.encode(JSON.stringify(candidate)).byteLength + (files.length ? 1 : 0);
    if (requestBytes + size > MAX_SOURCE_CONTEXT_REQUEST_BYTES) {
      skipped.push({ path: entry.path, reason: "request-size-limit" });
      continue;
    }
    requestBytes += size;
    files.push(candidate);
  }
  return { files, selectedCount: selection.selectedCount, readCount, skipped, body: JSON.stringify({ sourceContext: { files } }) };
}

function appendSafeTextItems(list, entries) {
  const fragment = document.createDocumentFragment();
  for (const text of entries) { const item = document.createElement("li"); item.textContent = text; fragment.append(item); }
  list.replaceChildren(fragment);
}

function renderSourceReview(record, selection) {
  const review = record?.sourceReview && typeof record.sourceReview === "object" ? record.sourceReview : {};
  const status = String(review.status || "NOT_REQUESTED").toUpperCase();
  const hasSelection = Boolean(selection?.candidates?.length);
  const canWriteFiles = typeof window.showDirectoryPicker === "function"
    || typeof window.showOpenFilePicker === "function";
  const terminal = ["BLOCKED", "COMPLETED", "INCONCLUSIVE"].includes(String(record?.status).toUpperCase());
  const coverage = record?.evidenceHandoff?.stats?.coverage ?? record?.stoppingPoint?.coverage ?? {};
  const observed = Number.isFinite(coverage.controlsObserved) ? coverage.controlsObserved : coverage.areasObserved;
  const expected = Number.isFinite(coverage.controlsExpected) ? coverage.controlsExpected : coverage.areasExpected;
  const score = Number.isFinite(coverage.scorePercentage)
    ? coverage.scorePercentage
    : Number.isFinite(observed) && Number.isFinite(expected) && expected > 0
      ? Math.round((observed / expected) * 100) : null;
  const needsFix = score !== null && score < 100;
  const hasSavedBaseline = status === "PATCH_READY" && hasPersistedSourceBaseline(review);
  const actions = getSourceReviewActions(status, hasSelection, reviewedSourceFiles.length > 0 || hasSavedBaseline);
  sourceReviewResult.hidden = !actions.showSavedReview && !(terminal && needsFix);
  if (sourceReviewResult.hidden) return;
  const labels = { NOT_REQUESTED: "Ready to review", IN_PROGRESS: "Review in progress", PATCH_READY: "Patch ready", NO_PATCH: "No patch produced", FAILED: "Review failed", CANCELLED: "Review cancelled" };
  sourceReviewFixButton.hidden = !actions.showFix && !(terminal && needsFix && status === "NOT_REQUESTED");
  sourceReviewFixButton.textContent = status === "NOT_REQUESTED" ? "Fix" : "Retry Fix";
  sourceReviewFixButton.disabled = sourceReviewBusy || !hasSelection;
  sourceReviewApproveButton.hidden = !actions.showApprove || !canWriteFiles;
  sourceReviewApproveButton.disabled = sourceReviewBusy;
  sourceReviewStatus.textContent = !hasSelection && needsFix && status === "NOT_REQUESTED" ? "Source files needed" : labels[status] || "Review ended";
  sourceReviewStatus.dataset.status = status.toLowerCase();
  sourceReviewSummary.textContent = typeof review.summary === "string" && review.summary
    ? review.summary
    : hasSelection ? "Ready to review."
      : "Select source files, then press Fix.";
  if (status === "PATCH_READY" && !canWriteFiles) {
    sourceReviewActionStatus.textContent = "This browser blocks direct file writes. Download the patch to apply the reviewed changes.";
  }
  sourceReviewRootCauseBlock.hidden = typeof review.rootCause !== "string" || !review.rootCause.trim();
  sourceReviewRootCause.textContent = sourceReviewRootCauseBlock.hidden ? "" : review.rootCause;
  sourceReviewProposedFixBlock.hidden = typeof review.proposedFix !== "string" || !review.proposedFix.trim();
  sourceReviewProposedFix.textContent = sourceReviewProposedFixBlock.hidden ? "" : review.proposedFix;
  const patch = typeof review.patch === "string" ? review.patch : "";
  const changedPaths = [...patch.matchAll(/^diff --git a\/(.+) b\/(.+)$/gm)].map(([, , path]) => path);
  const paths = status === "PATCH_READY"
    ? changedPaths
    : Array.isArray(review.relevantPaths) ? review.relevantPaths.filter((path) => typeof path === "string") : [];
  sourceReviewRelevantBlock.hidden = !paths.length;
  sourceReviewFilesLabel.textContent = status === "PATCH_READY" ? "Files to change" : "Files reviewed";
  appendSafeTextItems(sourceReviewRelevantPaths, paths);
  sourceReviewPatchBlock.hidden = status !== "PATCH_READY" || !patch.trim();
  sourceReviewPatch.textContent = sourceReviewPatchBlock.hidden ? "" : patch;
  sourcePatchDownload.hidden = sourceReviewPatchBlock.hidden;
  if (sourcePatchUrl) URL.revokeObjectURL(sourcePatchUrl);
  sourcePatchUrl = null;
  if (!sourceReviewPatchBlock.hidden) {
    sourcePatchUrl = URL.createObjectURL(new Blob([patch], { type: "text/x-diff;charset=utf-8" }));
    sourcePatchDownload.href = sourcePatchUrl;
    sourcePatchDownload.download = "access-trace-source-review.patch";
  } else sourcePatchDownload.removeAttribute("href");
}

async function handleSourceFix() {
  if (!latestRunRecord?.id || sourceReviewBusy || workflowInProgress || !latestSourceSelection.length) return;
  const runId = latestRunRecord.id;
  sourceReviewBusy = true;
  sourceReviewFixButton.disabled = true;
  sourceReviewActionStatus.textContent = "Reviewing files…";
  try {
    const prepared = await prepareSourceContext(latestSourceSelection);
    if (!prepared.files.length) throw new Error("No eligible text files were available for review.");
    if (latestRunRecord?.id !== runId) throw new Error("The active report changed. Run Fix again on the current report.");
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/source-review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: prepared.body,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result?.error?.message || "The source review could not be completed.");
    if (latestRunRecord?.id !== runId || result?.id !== runId) throw new Error("The source review response did not match the active report.");
    latestRunRecord = result;
    reviewedSourceFiles = prepared.files.map(({ path, content }) => ({ path, content }));
    renderSourceReview(result, { ...prepared, candidates: latestSourceSelection });
    const serialized = JSON.stringify(result, null, 2);
    liveRecordJson.textContent = serialized;
    if (liveRecordUrl) URL.revokeObjectURL(liveRecordUrl);
    liveRecordUrl = URL.createObjectURL(new Blob([serialized], { type: "application/json" }));
    liveRecordDownload.href = liveRecordUrl;
    liveRecordDownload.hidden = false;
    sourceReviewActionStatus.textContent = result.sourceReview?.status === "FAILED"
      ? "Review failed. You can retry Fix."
      : result.sourceReview?.status === "PATCH_READY"
        && typeof window.showDirectoryPicker !== "function"
        && typeof window.showOpenFilePicker !== "function"
        ? "Review complete. This browser blocks direct file writes; download the patch to apply it manually."
        : "Review the patch, then approve.";
    sourceReviewResult.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    sourceReviewResult.hidden = false;
    sourceReviewStatus.textContent = "Review failed";
    sourceReviewSummary.textContent = error instanceof Error ? error.message : "The source review could not be completed.";
    sourceReviewFixButton.hidden = false;
    sourceReviewFixButton.textContent = "Retry Fix";
    sourceReviewApproveButton.hidden = true;
    sourceReviewActionStatus.textContent = "You can retry Fix.";
  } finally {
    sourceReviewBusy = false;
    sourceReviewFixButton.disabled = false;
    sourceReviewApproveButton.disabled = false;
  }
}

async function lookupDirectoryFile(rootHandle, path) {
  if (!isSafeSourcePath(path)) throw new Error(`Unsafe file path in approved patch: ${path}`);
  const parts = path.split("/");
  let directory = rootHandle;
  for (const part of parts.slice(0, -1)) directory = await directory.getDirectoryHandle(part);
  return directory.getFileHandle(parts.at(-1));
}

async function sha256Text(value) {
  if (!window.crypto?.subtle) throw new Error("This browser cannot verify the saved source baseline. Download the patch to apply it manually.");
  const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function refreshUploadedAssessmentCopy(changedFiles) {
  let target;
  try { target = new URL(targetInput.value); } catch { return false; }
  const match = target.pathname.match(/^\/sites\/[^/]+\/(.+)$/);
  if (!match || !uploadedLocalSourceFiles.length) return false;
  const entrypoint = decodeURIComponent(match[1]);
  const byPath = new Map(changedFiles.map((file) => [file.path, file]));
  if ([...byPath.keys()].some((path) => !uploadedLocalSourceFiles.some((file) => file.path === path))) return false;

  const entries = [];
  for (const original of uploadedLocalSourceFiles) {
    const changed = byPath.get(original.path);
    const file = changed ? await changed.handle.getFile() : original.file;
    entries.push({ file, path: original.path, selectionType: "page" });
  }
  if (!entries.some((entry) => entry.path === entrypoint)) return false;

  const body = new FormData();
  body.append("entrypoint", entrypoint);
  for (const { file, path } of entries) body.append("files", file, path);
  const response = await fetch("/api/sites", { method: "POST", body });
  const result = await response.json();
  if (!response.ok) throw new Error(result?.error?.message || "Assessment copy could not be refreshed.");

  targetInput.value = result.targetUrl;
  uploadedLocalSourceFiles = entries;
  updateRecognizedTargetLabel();
  clearTargetValidationError();
  targetSiteStatus.textContent = "Assessment copy updated. Run it again to verify the fix.";
  return true;
}

async function handleSourceFixApproval() {
  if (!latestRunRecord?.id || sourceReviewBusy || !canApproveSourceReview(reviewedSourceFiles.length, latestRunRecord?.sourceReview)) return;
  const runId = latestRunRecord.id;
  const review = latestRunRecord.sourceReview;
  const reviewSnapshot = JSON.stringify(review);
  const baselines = reviewedSourceFiles.map(({ path, content }) => ({ path, content }));
  const assertCurrent = () => {
    if (latestRunRecord?.id !== runId || latestRunRecord.sourceReview !== review || JSON.stringify(review) !== reviewSnapshot) {
      throw new Error("The report or proposal changed during approval. Review it again before applying.");
    }
  };
  const canPickDirectory = typeof window.showDirectoryPicker === "function";
  const canPickFiles = typeof window.showOpenFilePicker === "function";
  if (!canPickDirectory && !canPickFiles) {
    sourceReviewActionStatus.textContent = "This browser does not allow AccessTrace to write selected files. Use Download patch to apply the reviewed changes.";
    return;
  }
  sourceReviewBusy = true;
  sourceReviewFixButton.disabled = true;
  sourceReviewApproveButton.disabled = true;
  let root;
  try {
    const fileHandles = canPickDirectory ? null : await window.showOpenFilePicker({ multiple: true });
    if (canPickDirectory) {
      root = await window.showDirectoryPicker({ mode: "readwrite" });
      let permission = typeof root.queryPermission === "function" ? await root.queryPermission({ mode: "readwrite" }) : "prompt";
      if (permission !== "granted" && typeof root.requestPermission === "function") permission = await root.requestPermission({ mode: "readwrite" });
      if (permission !== "granted") throw new Error("Write access was not granted. No files were changed.");
    }
    assertCurrent();
    let sources = baselines;
    const handles = new Map();
    if (!sources.length) {
      const paths = Array.isArray(review.relevantPaths) ? review.relevantPaths : [];
      const digests = review.sourceDigests || {};
      if (!paths.length || paths.some((path) => typeof digests[path] !== "string")) throw new Error("The saved proposal has no verifiable source baseline. Download the patch to apply it manually.");
      sources = [];
      for (const path of paths) {
        const candidates = canPickDirectory
          ? [await lookupDirectoryFile(root, path)]
          : fileHandles.filter((handle) => handle.name === path.split("/").at(-1));
        if (candidates.length !== 1) throw new Error(`Select exactly one reviewed file named ${path.split("/").at(-1)}. No files were changed.`);
        const handle = candidates[0];
        if (!canPickDirectory) {
          let permission = typeof handle.queryPermission === "function" ? await handle.queryPermission({ mode: "readwrite" }) : "prompt";
          if (permission !== "granted" && typeof handle.requestPermission === "function") permission = await handle.requestPermission({ mode: "readwrite" });
          if (permission !== "granted") throw new Error(`Write access was not granted for ${path}. No files were changed.`);
        }
        const content = await (await handle.getFile()).text();
        if (await sha256Text(content) !== digests[path]) throw new Error(`${path} differs from the saved review. No files were changed.`);
        sources.push({ path, content });
        handles.set(path, handle);
      }
    }
    for (const baseline of sources) {
      let handle = handles.get(baseline.path);
      if (!handle) {
        const candidates = canPickDirectory
          ? [await lookupDirectoryFile(root, baseline.path)]
          : fileHandles.filter((item) => item.name === baseline.path.split("/").at(-1));
        if (candidates.length !== 1) throw new Error(`Select exactly one reviewed file named ${baseline.path.split("/").at(-1)}. No files were changed.`);
        [handle] = candidates;
        if (!canPickDirectory) {
          let permission = typeof handle.queryPermission === "function" ? await handle.queryPermission({ mode: "readwrite" }) : "prompt";
          if (permission !== "granted" && typeof handle.requestPermission === "function") permission = await handle.requestPermission({ mode: "readwrite" });
          if (permission !== "granted") throw new Error(`Write access was not granted for ${baseline.path}. No files were changed.`);
        }
      }
      if (await (await handle.getFile()).text() !== baseline.content) throw new Error(`${baseline.path} changed since review. No files were changed; run Fix again.`);
      handles.set(baseline.path, handle);
    }
    assertCurrent();
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/source-fix-approve`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sourceContext: { files: sources } }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result?.error?.message || "The approved patch could not be prepared.");
    assertCurrent();
    const changedFiles = validateApplicableFiles(sources, result.appliableFiles);
    const writable = [];
    for (const changed of changedFiles) {
      const baseline = sources.find((file) => file.path === changed.path);
      const handle = handles.get(changed.path);
      if (!baseline || !handle) throw new Error(`The patch refers to an unreviewed file: ${changed.path}. No files were changed.`);
      if (await (await handle.getFile()).text() !== baseline.content) throw new Error(`${changed.path} changed since review. No files were changed; run Fix again.`);
      writable.push({ path: changed.path, content: changed.content, handle });
    }
    const written = [];
    for (const target of writable) {
      const stream = await target.handle.createWritable();
      try {
        await stream.write(target.content);
        await stream.close();
        written.push(target.path);
      } catch (error) {
        try { await stream.abort(error); } catch {}
        const detail = error instanceof Error ? error.message : "Write failed.";
        throw new Error(written.length
          ? `Writing stopped at ${target.path}; already changed: ${written.join(", ")}. ${detail}`
          : `Could not write ${target.path}; no files were changed. ${detail}`);
      }
    }
    sourceReviewStatus.textContent = "Retest needed";
    sourceReviewStatus.dataset.status = "applied";
    sourceReviewApproveButton.hidden = true;
    try {
      const refreshed = await refreshUploadedAssessmentCopy(writable);
      sourceReviewActionStatus.textContent = refreshed
        ? `Applied to ${written.join(", ")}. Assessment copy updated; run it again to verify.`
        : `Applied to ${written.join(", ")}. Re-upload the changed files before retesting.`;
    } catch {
      sourceReviewActionStatus.textContent = `Applied to ${written.join(", ")}; assessment copy not refreshed. Re-upload the changed files to retest.`;
    }
  } catch (error) {
    sourceReviewActionStatus.textContent = error instanceof Error ? error.message : "The patch could not be applied. No files were changed.";
  } finally {
    sourceReviewBusy = false;
    sourceReviewFixButton.disabled = false;
    sourceReviewApproveButton.disabled = false;
  }
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
    uploadedLocalSourceFiles = entries.map(({ file, path }) => ({ file, path, selectionType: "page" }));
    updateSourceContextSelection();
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
  const sourceSelectionForRun = analyzeSourceSelection(selectedSourceFiles).candidates;

  setActiveView("live");
  setWorkflowBusy(true);
  liveTerminal.hidden = false;
  liveResult.hidden = true;
  sourceReviewResult.hidden = true;
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
    latestSourceSelection = ["BLOCKED", "COMPLETED", "INCONCLUSIVE"].includes(String(result.status).toUpperCase())
      ? sourceSelectionForRun : [];
    reviewedSourceFiles = [];
    renderRunReport(result, liveRunReport);
    renderSourceReview(result, latestSourceSelection.length
      ? { selectedCount: sourceSelectionForRun.length, candidates: latestSourceSelection, skipped: analyzeSourceSelection(selectedSourceFiles).skipped }
      : null);
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
sourceContextFilesInput.addEventListener("change", () => {
  sourceContextDirectoryInput.value = "";
  updateSourceContextSelection();
});
sourceContextDirectoryInput.addEventListener("change", () => {
  sourceContextFilesInput.value = "";
  updateSourceContextSelection();
});
sourceReviewFixButton.addEventListener("click", handleSourceFix);
sourceReviewApproveButton.addEventListener("click", handleSourceFixApproval);
cancelLiveAssessmentButton.addEventListener("click", handleCancelLiveAssessment);
targetInput.addEventListener("input", () => {
  uploadedLocalSourceFiles = [];
  updateSourceContextSelection();
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
