# 06 — Deliver the report-ready evidence handoff

**What to build:** Every supported scope and terminal outcome produces a durable, redacted run record that the independent Report & Comparison workstream can consume without knowing Journey & Evidence implementation details. The handoff supports fixed completed, broken blocked, whole-site, goal-focused, inconclusive, and agent-failed evidence states.

**Blocked by:** 03 — Classify the broken contact-form barrier; 04 — Run whole-site and free-text goal assessments; 05 — Handle planner, browser, and lifecycle failures as inconclusive

**Status:** ready-for-agent

- [ ] The record carries target, assessment scope, optional goal, `simulationMode`, timestamps, duration, interaction count, ordered redacted actions, focus observations, coverage or goal progress, stopping point, stopping screenshot reference, warnings, recovery evidence, terminal state, and agent-failure context.
- [ ] Field identity, focus relationship, character counts, accepted-input state, and observed validation state remain available without retaining raw values.
- [ ] Stopping screenshots omit or visibly redact editable values before persistence.
- [ ] The handoff preserves evidence references and terminal context needed for downstream explanation, proposed-fix decisions, confidence, score/metric presentation, and configurable comparison consistency.
- [ ] Representative completed, blocked, inconclusive, whole-site, and goal-focused records can replace report samples without changing the shared evidence contract.
