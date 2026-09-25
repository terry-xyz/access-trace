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
