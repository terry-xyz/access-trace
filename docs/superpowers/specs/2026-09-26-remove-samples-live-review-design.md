# Remove Sample Reports and Use Real Run Reviews

## Purpose

AccessTrace should show evidence from assessments that actually ran. The sample report and sample comparison currently present invented runs, statistics, evidence, and fixes alongside the live workflow. Replace those views with reports built from persisted run records.

## User experience

- Remove the sample report and sample-only navigation and actions.
- Keep the comparison view. It runs the built-in broken and fixed demos for real, using the configured goal, simulation mode, and Low, Medium, or High run count.
- Show every comparison run separately and summarize only the completed run records. Each run has its own statistics, evidence, and review.
- A single assessment and every run inside a comparison receive the same real-run report.

## Run statistics

Compute displayed statistics from the run record. Include terminal status, duration, keyboard interaction count, success-condition result, and the available coverage or goal progress counts. Keep ordered actions, focus observations, recovery evidence, and warnings tied to their recorded values.

The current run contract does not record pass/fail observations for general accessibility criteria. Do not turn its raw action or coverage counts into an accessibility grade or invented named metric rates.

## Evidence review

After each assessment, run a separate evidence-review step. It receives only the bounded, redacted assessment context and evidence already retained for the run: actions, observations, stopping point, screenshot, warnings, and recovery evidence. It returns a short outcome explanation, evidence references, confidence, and a specific proposed fix when the recorded evidence supports one. When it does not, the review explicitly reports that no supported fix is available.

Persist the review on the run record alongside its evidence handoff. The report links review claims to evidence from that same run. Comparison summaries and per-run reports use the reviews stored on their respective run records.

## Failure handling

If evidence review fails or returns invalid output, retain and show the completed run and its real statistics. Mark the review unavailable for that run; do not substitute sample copy or imply that a review occurred.

If an assessment fails before returning a run record, show the execution error and do not display report data from another run.

## Boundaries

The built-in fixed and broken pages remain actual assessment targets. Existing target validation, keyboard-only execution, simulation setting, and evidence redaction continue to govern real runs. Reports describe only evidence for the configured local assessment and do not claim general accessibility or WCAG conformance.
