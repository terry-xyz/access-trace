const TARGET = "https://example.test/newsletter";
const focus = (role, accessibleName, stableId) => ({ role, accessibleName, stableId, isStable: true });
const controls = [
  focus("link", "Home", "home"),
  focus("textbox", "Email", "email"),
  focus("button", "Subscribe", "subscribe"),
  focus("link", "Privacy", "privacy"),
];
const observations = [focus("document", "Newsletter", "document"), ...controls.filter((item) => item.stableId !== "subscribe")]
  .map((item) => ({ url: TARGET, title: "Illustrative newsletter page", focus: item }));
const actions = observations.slice(1).map((_, index) => ({
  sequence: index + 1, kind: "key", key: "Tab", status: "delivered", focusBefore: observations[index].focus,
}));
const references = [{ kind: "action", sequence: 3, id: "action:3" }, { kind: "observation", sequence: 4, id: "observation:4" }];

export const EXAMPLE_RUN = {
  id: "DEMO-NEWSLETTER",
  provenance: "Illustrative walkthrough data; no browser assessment or Codex review took place.",
  status: "COMPLETED",
  targetUrl: TARGET,
  targetVersion: "web",
  assessmentScope: "whole-site",
  goal: null,
  pageOnly: true,
  headedMode: false,
  sitePageLimit: 1,
  simulationMode: true,
  durationMs: 12000,
  interactionCount: 3,
  actions,
  observations,
  warnings: [{ kind: "illustrative-coverage", message: "Example result: three of four controls reached. This is illustrative data, not a real assessment." }],
  stoppingPoint: {
    coverage: { status: "partial", completed: false, controlsObserved: 3, controlsExpected: 4, areasObserved: 1, areasExpected: 1, scorePercentage: 75 },
  },
  evidenceHandoff: {
    reporting: {
      status: "available",
      explanation: "Illustrative finding: Tab moves from Email directly to Privacy, skipping Subscribe. The example proposes replacing the custom control with a native button.",
      confidence: "medium",
      proposedFix: "Use a native submit button so Subscribe participates in keyboard navigation.",
      evidenceReferences: references,
      conditions: [{
        condition: "Illustrative finding: Subscribe is skipped during keyboard navigation.",
        mappingStatus: "mapped",
        wcagCriterion: { id: "2.1.1", name: "Keyboard", url: "https://www.w3.org/TR/WCAG22/#keyboard" },
        evidenceReferences: references,
      }],
    },
  },
  sourceReview: {
    status: "PATCH_READY",
    summary: "Illustrative proposal. Review the example patch below or download it; no source files were read or changed.",
    rootCause: "The example uses a custom Subscribe control with a negative tab index.",
    proposedFix: "Replace it with a native submit button.",
    relevantPaths: ["index.html"],
    patch: 'diff --git a/index.html b/index.html\n--- a/index.html\n+++ b/index.html\n@@ -1 +1 @@\n-<div role="button" tabindex="-1">Subscribe</div>\n+<button type="submit">Subscribe</button>\n',
  },
};

// ponytail: one example run at a time; use per-run state if more walkthroughs are added.
let currentRun = structuredClone(EXAMPLE_RUN);
const json = (value, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { "Content-Type": "application/json" },
});

/** Every demo request stays in memory; unsupported live operations fail locally. */
export async function demoFetch(path, options = {}) {
  options.signal?.throwIfAborted();
  const method = options.method ?? "GET";
  if (method === "GET" && path === "/api/config") return json({ defaultSitePageLimit: 1 });
  if (method === "GET" && path === "/api/runs/latest") return json(currentRun);
  if (method === "POST" && path === "/api/runs") {
    let configuration;
    try { configuration = JSON.parse(options.body); } catch { return json({ error: { message: "Invalid example settings." } }, 400); }
    if (configuration?.targetUrl !== TARGET || configuration.goal !== null || configuration.pageOnly !== true) {
      return json({ error: { message: "This walkthrough uses the fixed newsletter example. Run AccessTrace locally to assess your own pages." } }, 400);
    }
    currentRun = { ...structuredClone(EXAMPLE_RUN), status: "IN_PROGRESS" };
    return json(currentRun, 201);
  }
  const runPath = `/api/runs/${EXAMPLE_RUN.id}`;
  if (method === "GET" && path === runPath) return json(currentRun);
  if (method === "GET" && path === `${runPath}/activity`) {
    return json({ events: [{ sequence: 1, message: "Walkthrough: replaying the illustrative Tab sequence — Home, Email, Privacy." }] });
  }
  if (method === "POST" && path === `${runPath}/execute`) {
    await new Promise((resolve) => setTimeout(resolve, 800));
    currentRun.status = "COMPLETED";
    return json(currentRun);
  }
  return json({ error: { message: "Live assessments, file uploads, and source edits require the local AccessTrace app." } }, 501);
}

export function configureDemo() {
  document.querySelector("#target-url").value = TARGET;
  document.querySelector("#target-url").readOnly = true;
  document.querySelector("#assessment-goal").readOnly = true;
  document.querySelector("#site-page-limit").readOnly = true;
  document.querySelector("#page-only").checked = true;
  document.querySelector("#target-url").dispatchEvent(new Event("input"));
  document.querySelector("#page-only").dispatchEvent(new Event("change"));
  document.querySelector("#setup-heading").textContent = "Explore the walkthrough";
  document.querySelector("#submit-label").textContent = "Play walkthrough";
  document.querySelector("#live-assessment-heading").textContent = "Replaying illustrative results";
  document.querySelector(".terminal-window-bar strong").textContent = "access-trace / walkthrough";
  document.querySelector("#assessment-goal").placeholder = "This example checks keyboard reachability.";
  document.querySelector("#source-review-heading").textContent = "Example source fix";
  document.querySelector("#new-assessment").textContent = "Replay walkthrough →";
  document.querySelector(".site-footer span").textContent = "AccessTrace · illustrative demo";
}
