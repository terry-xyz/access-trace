# Remove Sample Reports and Use Real Run Reviews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove sample-driven report screens and show persisted statistics and evidence reviews for each actual assessment, including the built-in broken-versus-fixed comparison.

**Architecture:** Keep the journey runner responsible for browser evidence. Add a separate bounded Codex review call after each run and persist its validated result in the run's evidence handoff. Render run facts and reviews from the returned records, and orchestrate comparisons by executing the configured number of real runs against both built-in demos.

**Tech Stack:** Python standard library HTTP server and JSON records; browser JavaScript modules; the existing Codex CLI subprocess boundary; HTML and CSS.

---

## File map

- `access_trace/planner.py` — retain the existing restricted Codex CLI behavior and expose a structured-output call reusable by a separate review role.
- `access_trace/report.py` — build the bounded review prompt, schema-check model output, resolve only real evidence references, and attach the redacted stopping screenshot when available.
- `access_trace/evidence.py` — project run statistics and persisted review fields into the stable `evidenceHandoff` without dropping a prior review when a record is saved again; provide stable locators for action, observation, recovery, and screenshot citations.
- `access_trace/server.py` — invoke the review after each terminal browser run, preserve the run when review fails, and return the final saved record.
- `index.html` — remove sample navigation and report markup; provide reusable live-run report markup and a real comparison result surface.
- `src/main.mjs` — remove sample rendering and replace it with renderers for actual records and sequential real comparison runs.
- `src/live-comparison.mjs` — summarize actual broken/fixed run records without inventing score or metric data.
- `src/styles.css` — remove sample-only presentation and style the live report and actual comparison records.
- `access_trace/server.py` static asset map — serve `src/live-comparison.mjs`; stop exposing the sample report module to the browser.
- `src/sample-report.mjs` — keep only if existing Node tests still import it; it must not be imported or served by the application UI.

## Task 1: Add an evidence-only Codex review

**Files:**
- Modify: `access_trace/planner.py`
- Create: `access_trace/report.py`

- [x] Generalize the existing structured Codex response path to accept a caller-provided output schema while preserving its read-only sandbox, disabled tools, bounded output, timeout, environment allowlist, and cancellation behavior.
- [x] Add a review result schema with `explanation`, `evidenceReferences`, `confidence`, and nullable `proposedFix`. Derive stable citation IDs from the run's action, observation, recovery, and screenshot locators, return each accepted citation with its UI locator, and reject an unknown ID or malformed review. Recovery IDs use their 1-based position in the sanitized recovery list.
- [x] Build the prompt from `evidenceHandoff.assessment`, `actions`, `observations`, `stopping`, and `terminal` only. Read the stopping screenshot from the run evidence directory only after checking that the resolved path remains within that directory, its size is bounded, and it has a PNG signature.
- [x] Ask the review role to describe only recorded evidence, include a specific fix only when supported, and return `proposedFix: null` when evidence is insufficient.
- [x] Keep model errors and malformed output as a bounded review error; do not put raw CLI diagnostics into a persisted record.

## Task 2: Persist review status alongside actual run facts

**Files:**
- Modify: `access_trace/evidence.py`
- Modify: `access_trace/server.py`
- Modify: `access_trace/store.py`

- [x] Project the existing record facts into a stable `stats` object: terminal status, duration, interaction count, goal progress, coverage, action count, observation count, and recovery count. Leave unavailable values null instead of converting them to zero.
- [x] Set initial reporting state to pending. On a valid review, persist its explanation, evidence references, confidence, and proposed fix under `evidenceHandoff.reporting` with status `available`; on reviewer failure, persist status `unavailable` and a fixed user-safe reason.
- [x] Preserve the reporting object when `RunStore.save()` refreshes the evidence handoff so a later save cannot erase a completed review.
- [x] Run the separate review after browser execution reaches a terminal state. Save the run whether review succeeds or fails, then return the saved run to the browser.
- [x] Keep run status and real stats intact when review is unavailable. Keep the review operation identifiable so stop/cancel requests do not rewrite a completed browser result as inconclusive.

## Task 3: Replace the sample report screen with actual run reports

**Files:**
- Modify: `index.html`
- Modify: `src/main.mjs`

- [x] Remove the Sample report navigation button, setup action, help text, sample notice, report preview, sample download link, and sample-only target/configuration copy.
- [x] Remove the sample report renderer and its imports from `src/main.mjs`; keep validation, uploaded-local-HTML selection, live run progress, and run cancellation. Leave the current comparison wiring in place for the next task, which replaces it and removes any remaining sample-report imports.
- [x] Refactor the live result renderer to accept a run record and a root element. Display status, duration, action count, coverage or goal field progress, success-condition result, warnings, ordered actions, focus observations, recovery checks, and the actual review state.
- [x] Render review explanation and confidence only from `evidenceHandoff.reporting`. Link each allowed evidence reference to its matching action, observation, recovery item, or stopping screenshot in that same report, including a stable recovery anchor based on the 1-based sanitized recovery-list position.
- [x] Show “No evidence-supported fix available” for a successful review with a null fix. Show “Review unavailable” for a failed review; never fall back to sample or generic generated review text.
- [x] Retain the current run-record download and ensure each displayed run report is populated only from the response for that run.

## Task 4: Turn Compare into real broken/fixed assessments

**Files:**
- Create: `src/live-comparison.mjs`
- Modify: `src/main.mjs`
- Modify: `index.html`
- Modify: `access_trace/server.py`

- [x] Keep Low/Medium/High and map them to one, two, or three runs per demo. Execute paired slots sequentially in this order: broken run 1, fixed run 1, broken run 2, fixed run 2, broken run 3, fixed run 3, stopping at the configured count. Send the same goal and simulation setting in every create request.
- [x] For each slot, create a fresh run through `/api/runs` and execute it through the existing endpoint. Retain only that slot's returned record. If creation or execution fails, store `{record: null, error: <safe message>}` for that slot and attempt every remaining slot; review unavailability still retains the real record and does not stop later runs. Never pass a failed slot or a prior slot's record to the report renderer.
- [x] Add a pure summary function in `src/live-comparison.mjs` that counts actual terminal statuses, groups recorded coverage count pairs/statuses, and counts success outcomes as reached, not reached, not recorded, or not configured. Count execution failures separately from terminal statuses. Keep missing values explicit; do not compute averages, ratios, scores, or pass rates.
- [x] Render comparison settings, configured and processed slot counts, every returned run record, each explicit error slot, and each record's own evidence review through the Task 3 renderer. Label the sides “Broken demo” and “Fixed demo”; remove the `src/comparison.mjs`/`buildSiteComparison` integration, sample provenance, duplicated sample evidence, metric deltas, and representative-run copy.
- [x] Show progress across every sequential slot. Poll the persisted run record while `/execute` waits for its review; hide/disable Stop once that record reaches terminal status and show review-in-progress. Keep cancellation attached only to the captured ID of a currently executing browser run; after that request returns (including an inconclusive cancellation record), continue with later slots. Apply the same browser-versus-review stop boundary to a single live run. Hide/disable stop controls between browser runs. Restore navigation and form controls when the comparison finishes or errors.

## Task 5: Remove sample-only assets and presentation

**Files:**
- Modify: `src/styles.css`
- Modify: `access_trace/server.py`
- Modify: `index.html`
- Modify: `src/main.mjs`

- [x] Replace sample-report, sample-comparison, and fake score/metric styles with styles for actual run statistics, review status, evidence references, and comparison groups.
- [x] Serve `src/live-comparison.mjs` from the static asset map and remove browser routes for both retired `src/sample-report.mjs` and `src/comparison.mjs`; retain their source files only while existing tests import them.
- [x] Search `index.html`, `src/main.mjs`, `src/styles.css`, and `access_trace/server.py` for `sample-report`, `sample-comparison`, `Representative sample`, `data-sample-`, and retired fixture routes; remove remaining user-facing sample paths while retaining test-only fixture imports.
- [x] Review the final diff against every requirement in the approved spec. Do not add or run tests in this session; the active session instruction permits tests only when the user asks to test or verify implementation.

## Plan self-review

- The sample-removal requirement maps to Tasks 3 and 5.
- Real run statistics and evidence reviews map to Tasks 1 through 3.
- Actual comparison runs and per-run reports map to Task 4.
- Review failure handling and persistence map to Task 2.
- No placeholder steps or undefined output fields remain; `evidenceHandoff.stats` and `evidenceHandoff.reporting` are defined in Task 2 before the UI consumes them.
