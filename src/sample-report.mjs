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
