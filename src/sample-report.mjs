import { calculateWebsiteScore, CONTROLLED_TARGET_URL } from "./assessment.mjs";

const metrics = [
  { name: "Keyboard reachability", passed: 6, attempted: 8 },
  { name: "Visible focus", passed: 4, attempted: 5 },
  { name: "Form labels and instructions", passed: 5, attempted: 5 },
  { name: "Focus order", passed: 3, attempted: 4 },
];

let passed = 0;
let attempted = 0;
for (const metric of metrics) {
  passed += metric.passed;
  attempted += metric.attempted;
}

export const WHOLE_SITE_SAMPLE = Object.freeze({
  runId: "SAMPLE-WS-01",
  target: CONTROLLED_TARGET_URL,
  scope: "whole-site",
  goal: null,
  terminalStatus: "COMPLETED",
  outcomeTitle: "Full declared coverage completed",
  coverage: "7 of 7 declared page regions checked",
  coverageStats: { checked: 7, total: 7 },
  passed,
  attempted,
  score: calculateWebsiteScore(passed, attempted),
  metrics,
  duration: "1 min 18 sec",
  interactionCount: 6,
  explanationTitle: "A repeatable focus visibility issue appeared.",
  explanation:
    "A repeated keyboard check placed focus on the Products navigation link without a visible indicator. This evidence supports a specific focus-indicator fix. The result describes this keyboard assessment only.",
  confidence: "Medium",
  confidenceContext: "Repeated focus observation; sample evidence only",
  proposedFixTitle: "Restore a visible focus indicator",
  proposedFix:
    "Give the Products navigation link a clear :focus-visible indicator that remains visible against its background.",
  wcagReference: {
    label: "2.4.7 Focus Visible (Level AA)",
    url: "https://www.w3.org/WAI/WCAG22/Understanding/focus-visible",
  },
  evidenceReferences: [
    { id: "ACT-03", label: "Tab reached the Products navigation link" },
    { id: "FOC-03", label: "Focus landed on Products without a visible indicator" },
    { id: "REC-01", label: "Repeat navigation confirmed the same observation" },
    { id: "SHOT-02", label: "Sample screenshot reference for the focus observation" },
  ],
  orderedActions: [
    { id: "ACT-01", key: "Tab", target: "Skip to content", result: "Reached; focus indicator visible", outcome: "passed" },
    { id: "ACT-02", key: "Tab", target: "Primary navigation", result: "Reached; focus indicator visible", outcome: "passed" },
    { id: "ACT-03", key: "Tab", target: "Products link", result: "Reached; focus indicator not visible", outcome: "failed" },
    { id: "ACT-04", key: "Tab", target: "Search field", result: "Reached; text caret visible", outcome: "passed" },
    { id: "ACT-05", key: "Shift+Tab", target: "Products link", result: "Returned to same focus state", outcome: "failed" },
    { id: "ACT-06", key: "Escape", target: "Page", result: "No open dialog; page state unchanged", outcome: "passed" },
  ],
  focusObservations: [
    { id: "FOC-02", target: "Primary navigation", role: "Navigation landmark", indicator: "Visible outline" },
    { id: "FOC-03", target: "Products", role: "Link", indicator: "No visible indicator observed" },
    { id: "FOC-04", target: "Search", role: "Search field", indicator: "Text caret visible" },
  ],
  screenshot: {
    id: "SHOT-02",
    title: "Focus visibility",
    siteName: "Northstar",
    navigation: [
      { label: "Home", focused: false },
      { label: "Products", focused: true },
      { label: "About", focused: false },
    ],
    description:
      "Illustrative sample screenshot showing the Products link in keyboard focus. It is a report mockup, not a captured browser image.",
  },
  agentFailures: [],
  recoveryEvidence: [
    { id: "REC-TAB", text: "Tab advanced focus from Products to Search." },
    { id: "REC-01", text: "Shift+Tab returned to Products and reproduced the missing focus indicator." },
    { id: "REC-ESC", text: "Escape was checked; no dialog was open and no recovery action was needed." },
  ],
  warnings: ["No browser lifecycle warnings are included in this representative sample."],
});

const updatedWholeSiteMetrics = [
  { name: "Keyboard reachability", passed: 8, attempted: 8 },
  { name: "Visible focus", passed: 5, attempted: 5 },
  { name: "Form labels and instructions", passed: 4, attempted: 5 },
  { name: "Focus order", passed: 4, attempted: 4 },
];

const updatedWholeSiteTotals = updatedWholeSiteMetrics.reduce(
  (totals, metric) => ({
    passed: totals.passed + metric.passed,
    attempted: totals.attempted + metric.attempted,
  }),
  { passed: 0, attempted: 0 },
);

/** AGENT_UPDATED_WHOLE_SITE_SAMPLE shows a higher score alongside a visible label regression. */
export const AGENT_UPDATED_WHOLE_SITE_SAMPLE = Object.freeze({
  runId: "SAMPLE-WS-UP-01",
  target: CONTROLLED_TARGET_URL,
  scope: "whole-site",
  goal: null,
  terminalStatus: "COMPLETED",
  outcomeTitle: "Keyboard reachability improved with a label regression",
  coverage: "7 of 7 declared page regions checked",
  coverageStats: { checked: 7, total: 7 },
  passed: updatedWholeSiteTotals.passed,
  attempted: updatedWholeSiteTotals.attempted,
  score: calculateWebsiteScore(updatedWholeSiteTotals.passed, updatedWholeSiteTotals.attempted),
  metrics: updatedWholeSiteMetrics,
  duration: "1 min 23 sec",
  interactionCount: 7,
  explanationTitle: "The score rose, but one form-label metric regressed.",
  explanation:
    "This representative updated-site result shows stronger keyboard reachability and visible focus. The Message field no longer exposes an accessible label, so the form-label metric regressed despite the higher overall score.",
  confidence: "Medium",
  confidenceContext: "Representative action and focus evidence; not a live assessment",
  proposedFixTitle: "Restore the Message field's accessible label",
  proposedFix:
    "Associate a visible label with the Message field so its purpose is available to keyboard and assistive-technology users.",
  wcagReference: {
    label: "1.3.1 Info and Relationships (Level A)",
    url: "https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships",
  },
  evidenceReferences: [
    { id: "ACT-UP-04", label: "The Message field's accessible label was missing" },
    { id: "FOC-UP-04", label: "The Message field had no accessible name" },
    { id: "SHOT-UP-01", label: "Sample screenshot reference for the updated result" },
  ],
  orderedActions: [
    { id: "ACT-UP-01", key: "Tab", target: "Skip to content", result: "Reached with visible focus", outcome: "passed" },
    { id: "ACT-UP-02", key: "Tab", target: "Primary navigation", result: "Reached with visible focus", outcome: "passed" },
    { id: "ACT-UP-03", key: "Tab", target: "Products link", result: "Reached with a visible focus indicator", outcome: "passed" },
    { id: "ACT-UP-04", key: "Tab", target: "Message field", result: "Reached, but no accessible label was available", outcome: "failed" },
    { id: "ACT-UP-05", key: "Tab", target: "Submit control", result: "Reached with visible focus", outcome: "passed" },
    { id: "ACT-UP-06", key: "Enter", target: "Form confirmation", result: "The visible confirmation was reached", outcome: "passed" },
  ],
  focusObservations: [
    { id: "FOC-UP-02", target: "Primary navigation", role: "Navigation landmark", indicator: "Visible outline" },
    { id: "FOC-UP-03", target: "Products", role: "Link", indicator: "Visible outline" },
    { id: "FOC-UP-04", target: "Message field", role: "Text area", indicator: "No accessible name announced" },
  ],
  screenshot: {
    id: "SHOT-UP-01",
    title: "Updated site focus and form result",
    siteName: "Northstar",
    navigation: [
      { label: "Home", focused: false },
      { label: "Products", focused: true },
      { label: "Contact", focused: false },
    ],
    description:
      "Illustrative sample screenshot reference for the updated result. It is not a captured browser image.",
  },
  agentFailures: [],
  recoveryEvidence: [
    { id: "REC-UP-01", text: "Tab reached the Message field; its accessible name remained unavailable on repeat." },
    { id: "REC-UP-02", text: "The remaining keyboard actions reached the Submit control and visible confirmation." },
  ],
  warnings: ["Representative sample evidence only; no browser run has taken place."],
});

const goalMetrics = [
  { name: "Planned goal actions", passed: 5, attempted: 6 },
  { name: "Keyboard reachability", passed: 5, attempted: 5 },
  { name: "Form labels and instructions", passed: 4, attempted: 4 },
];

const goalTotals = goalMetrics.reduce(
  (totals, metric) => ({
    passed: totals.passed + metric.passed,
    attempted: totals.attempted + metric.attempted,
  }),
  { passed: 0, attempted: 0 },
);

/** GOAL_FOCUSED_SAMPLE shows a completed sample goal with a website failure and a recovered agent failure. */
export const GOAL_FOCUSED_SAMPLE = Object.freeze({
  runId: "SAMPLE-GF-01",
  target: CONTROLLED_TARGET_URL,
  scope: "goal-focused",
  goal: "Submit the contact form using only the keyboard",
  terminalStatus: "COMPLETED",
  outcomeTitle: "The goal completed after one website check failed",
  coverage: "5 of 6 planned goal actions passed; the success condition was reached",
  coverageStats: { checked: 5, total: 6 },
  passed: goalTotals.passed,
  attempted: goalTotals.attempted,
  score: calculateWebsiteScore(goalTotals.passed, goalTotals.attempted),
  metrics: goalMetrics,
  duration: "52 sec",
  interactionCount: 6,
  explanationTitle: "The form was submitted after a focus check failed.",
  explanation:
    "The representative contact-form goal reached its visible confirmation. One website check found no visible focus indicator on the Email field; the assessment continued through the remaining planned actions. This sample does not assess the goal entered above.",
  confidence: "Medium",
  confidenceContext: "Sample action sequence and visible confirmation; not live evidence",
  proposedFixTitle: "Make the Email field focus indicator visible",
  proposedFix:
    "Add a clear :focus-visible style to the Email field so keyboard focus remains easy to locate.",
  wcagReference: {
    label: "2.4.7 Focus Visible (Level AA)",
    url: "https://www.w3.org/WAI/WCAG22/Understanding/focus-visible",
  },
  evidenceReferences: [
    { id: "ACT-GF-03", label: "The Email field had no visible focus indicator" },
    { id: "FOC-GF-03", label: "Focus observation for the Email field" },
    { id: "REC-GF-01", label: "Assessment continued after the failed check" },
    { id: "SHOT-GF-01", label: "Sample screenshot reference for the confirmation" },
  ],
  orderedActions: [
    { id: "ACT-GF-01", key: "Tab", target: "Contact form", result: "Reached the form; focus indicator visible", outcome: "passed" },
    { id: "ACT-GF-02", key: "Tab", target: "Name field", result: "Reached; field label announced", outcome: "passed" },
    { id: "ACT-GF-03", key: "Tab", target: "Email field", result: "Reached; no visible focus indicator observed", outcome: "failed" },
    { id: "ACT-GF-04", key: "Tab", target: "Message field", result: "Reached; focus indicator visible and label announced", outcome: "passed" },
    { id: "ACT-GF-05", key: "Tab", target: "Submit button", result: "Reached with visible focus", outcome: "passed" },
    { id: "ACT-GF-06", key: "Enter", target: "Submission confirmation", result: "Visible confirmation reached; goal completed", outcome: "passed" },
  ],
  focusObservations: [
    { id: "FOC-GF-01", target: "Name field", role: "Text field", indicator: "Visible outline" },
    { id: "FOC-GF-03", target: "Email field", role: "Email field", indicator: "No visible indicator observed" },
    { id: "FOC-GF-04", target: "Message field", role: "Text area", indicator: "Visible outline" },
  ],
  screenshot: {
    id: "SHOT-GF-01",
    title: "Contact form confirmation",
    siteName: "Northstar",
    navigation: [
      { label: "Home", focused: false },
      { label: "Contact", focused: true },
      { label: "Help", focused: false },
    ],
    description:
      "Illustrative sample screenshot reference for the contact form confirmation. It is not a captured browser image.",
  },
  agentFailures: ["A planner attempt timed out; its single retry completed from the same observation."],
  recoveryEvidence: [
    { id: "REC-GF-01", text: "After the Email focus check failed, Tab advanced to Message and assessment continued." },
    { id: "REC-GF-02", text: "The remaining planned actions reached the Submit control and visible confirmation." },
  ],
  warnings: ["No browser lifecycle warnings are included in this representative sample."],
});

const updatedGoalMetrics = [
  { name: "Planned goal actions", passed: 6, attempted: 6 },
  { name: "Keyboard reachability", passed: 5, attempted: 5 },
  { name: "Form labels and instructions", passed: 3, attempted: 4 },
];

const updatedGoalTotals = updatedGoalMetrics.reduce(
  (totals, metric) => ({
    passed: totals.passed + metric.passed,
    attempted: totals.attempted + metric.attempted,
  }),
  { passed: 0, attempted: 0 },
);

/** AGENT_UPDATED_GOAL_FOCUSED_SAMPLE retains a completed task and exposes its label regression. */
export const AGENT_UPDATED_GOAL_FOCUSED_SAMPLE = Object.freeze({
  ...GOAL_FOCUSED_SAMPLE,
  runId: "SAMPLE-GF-UP-01",
  outcomeTitle: "The form was submitted, with a label regression",
  coverage: "6 of 6 planned goal actions completed; one label check failed",
  coverageStats: { checked: 6, total: 6 },
  passed: updatedGoalTotals.passed,
  attempted: updatedGoalTotals.attempted,
  score: calculateWebsiteScore(updatedGoalTotals.passed, updatedGoalTotals.attempted),
  metrics: updatedGoalMetrics,
  duration: "54 sec",
  interactionCount: 7,
  explanationTitle: "The configured task completed, but a field label was missing.",
  explanation:
    "This representative updated-site result reached the visible confirmation. A check found that the Message field had no accessible label; the completed task does not erase that failed website check.",
  confidenceContext: "Representative action and focus evidence; not a live assessment",
  proposedFixTitle: "Restore the Message field's accessible label",
  proposedFix:
    "Associate a visible label with the Message field so its purpose is available to keyboard and assistive-technology users.",
  wcagReference: {
    label: "1.3.1 Info and Relationships (Level A)",
    url: "https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships",
  },
  evidenceReferences: [
    { id: "ACT-GFU-02", label: "The Message field's accessible label was missing" },
    { id: "FOC-GFU-02", label: "The Message field had no accessible name" },
    { id: "SHOT-GFU-01", label: "Sample screenshot reference for the updated confirmation" },
  ],
  orderedActions: [
    { id: "ACT-GFU-01", key: "Tab", target: "Name field", result: "Reached with visible focus", outcome: "passed" },
    { id: "ACT-GFU-02", key: "Tab", target: "Message field", result: "Reached, but no accessible label was available", outcome: "failed" },
    { id: "ACT-GFU-03", key: "Enter", target: "Form confirmation", result: "The visible confirmation was reached", outcome: "passed" },
  ],
  focusObservations: [
    { id: "FOC-GFU-01", target: "Name field", role: "Text field", indicator: "Visible outline" },
    { id: "FOC-GFU-02", target: "Message field", role: "Text area", indicator: "No accessible name announced" },
  ],
  screenshot: {
    id: "SHOT-GFU-01",
    title: "Updated contact form confirmation",
    siteName: "Northstar",
    navigation: [
      { label: "Home", focused: false },
      { label: "Contact", focused: true },
      { label: "Help", focused: false },
    ],
    description:
      "Illustrative sample screenshot reference for the updated confirmation. It is not a captured browser image.",
  },
  agentFailures: [],
  recoveryEvidence: [
    { id: "REC-GFU-01", text: "The Message field was revisited and still had no accessible name." },
    { id: "REC-GFU-02", text: "The Submit control was activated and the visible confirmation was reached." },
  ],
  warnings: ["Representative sample evidence only; no browser run has taken place."],
});
