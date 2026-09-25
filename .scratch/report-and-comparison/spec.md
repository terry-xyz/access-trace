# Report and Comparison Specification

## Problem Statement

Developers need a clear way to understand the results of a local-first keyboard accessibility assessment and to judge whether an agent-updated version of the same site improved. The result must be useful before live browser output exists, but it must not hide failed checks, inconsistent runs, agent failures, or incomplete evidence.

The report-and-comparison experience must support two assessment scopes:

- A whole-site assessment when no goal is supplied.
- A goal-focused assessment when the developer supplies a free-text goal.

The experience remains limited to the controlled local site and keyboard interaction. It may use relevant WCAG references as context, but it must not claim full WCAG conformance or general accessibility from the assessment.

## Solution

Provide a simple accessible setup, report, and comparison experience.

The developer confirms a controlled local target, optionally enters a goal, and confirms `simulationMode`, which is enabled by default. Without a goal, the autonomous agent checks the whole controlled site. With a goal, it takes all permitted actions toward that goal, continuing after website action failures.

The terminal report uses an outcome-first reading order. It always shows the terminal result, assessment scope, overall score, and named metric values before the detailed explanation and evidence. The score is:

> passed website checks ÷ attempted website checks × 100

Website failures affect the score. Agent failures are shown separately and do not affect the score. Browser and other non-agent tool failures are omitted and do not affect the score.

After an agent-updated version exists, the developer can compare it with the original version using identical assessment settings. The comparison uses a developer-configured consistency level, with Low as the default:

- Low: one assessment per version.
- Medium: two assessments per version.
- High: three assessments per version.

The comparison shows every run, each version’s score and metrics, score and metric changes, coverage context, average score, score range, evidence differences, and any inconsistent or inconclusive result. If some metrics improve while others worsen, the result is labeled `mixed result`.

## User Stories

1. As a developer, I want to enter or confirm the controlled local target, so that I know which site will be assessed.
2. As a developer, I want invalid, remote, off-loopback, or unrecognized targets rejected before a run starts, so that the assessment stays within the controlled local boundary.
3. As a developer, I want to run an assessment without entering a goal, so that the agent checks the whole controlled site.
4. As a developer, I want to enter a free-text goal, so that the agent assesses the specific outcome I care about.
5. As a developer, I want an unsupported or unsafe goal explained clearly, so that the agent does not silently reinterpret my request.
6. As a developer, I want to confirm `simulationMode`, enabled by default, so that I know the run is treated as a local simulation when enabled.
7. As a developer, I want `simulationMode` carried into the report and comparison, so that the context of every result is visible.
8. As a developer, I want the agent to continue after website action failures, so that the score reflects all attempted checks rather than stopping at the first problem.
9. As a developer, I want the report to state whether the whole-site assessment or supplied goal completed, so that I understand the terminal result.
10. As a developer, I want the report to show an overall score on every result, so that I can compare outcomes consistently.
11. As a developer, I want the score calculation to be visible through passed and attempted website checks, so that the score is understandable rather than opaque.
12. As a developer, I want named metric values shown beside the overall score, so that I can see what contributed to the result.
13. As a developer, I want a plain-English explanation near the top of the report, so that I can understand the result without reading every action first.
14. As a developer, I want ordered action evidence, focus observations, stopping-point evidence, screenshots, and recovery evidence available in the same report, so that I can inspect the explanation.
15. As a developer, I want long evidence sections to remain readable without moving to a separate report screen, so that the evidence stays connected to the conclusion.
16. As a developer, I want evidence references attached to explanations and proposed fixes, so that I can distinguish recorded facts from agent interpretation.
17. As a developer, I want confidence shown with the explanation, so that I understand how strongly the evidence supports it.
18. As a developer, I want a proposed fix shown only when the evidence supports one, so that the report does not invent remediation.
19. As a developer, I want relevant WCAG references shown beside evidence-backed findings, so that I have useful standards context without being told that the site conforms.
20. As a developer, I want agent failures shown separately from website failures, so that I can tell whether a low score reflects the site or the assessment agent.
21. As a developer, I want browser and other non-agent tool failures omitted from the report, so that they do not become misleading accessibility findings.
22. As a developer, I want target, scope, goal, simulation mode, duration, interaction count, coverage context, and saved-record information shown, so that the result is reproducible and understandable.
23. As a developer, I want to choose Low, Medium, or High consistency, so that I can trade assessment time for repeatability.
24. As a developer, I want Low consistency to be the default, so that the first comparison is quick.
25. As a developer, I want both original and updated versions assessed with exactly the same settings, so that the comparison is fair.
26. As a developer, I want the comparison to show original score, updated score, score change, metric changes, and coverage changes first, so that improvement is easy to judge.
27. As a developer, I want every repeated run visible alongside averages and ranges, so that inconsistent results are not hidden.
28. As a developer, I want inconclusive and agent-failed runs retained in the comparison, so that the comparison does not look more reliable than it is.
29. As a developer, I want a mixed result called out when metrics move in different directions, so that regressions are not hidden by a higher overall score.
30. As a developer, I want representative sample reports clearly labeled as not live assessments, so that sample data cannot be mistaken for browser evidence.
31. As a developer, I want representative whole-site, goal-focused, improved, mixed, incomplete, failed-step, and agent-failure states available before live output exists, so that the report experience can be developed independently.
32. As a developer, I want real Journey-and-Evidence results to replace sample values without changing the report contract, so that integration does not require redesigning the experience.
33. As a developer, I want clear labels, keyboard navigation, visible focus indicators, and understandable validation errors, so that the setup and report are themselves accessible.

## Implementation Decisions

- The owned product seam is the developer-facing assessment setup, terminal report, and original-versus-agent-updated comparison. Browser interaction, site traversal, evidence capture, run persistence, and barrier detection belong to the Journey and Evidence track.
- The setup has two assessment modes: whole-site when no goal is supplied, and goal-focused when a free-text goal is supplied.
- The target remains the controlled local site. Invalid or out-of-bound targets cannot start an assessment.
- `simulationMode` is enabled by default, remains a first-class run setting, and must be carried into reports and comparisons without weakening validation or failure handling.
- Website failures count toward the score. The agent continues through all planned goal actions or whole-site checks instead of stopping at the first website failure.
- The score is always displayed as passed website checks divided by attempted website checks, multiplied by 100. Passed and attempted counts must be visible.
- Agent failures are visible separately and do not change the score. Browser and other non-agent tool failures are omitted and do not change the score.
- The report is outcome-first and keeps supporting evidence in the same readable report. Long evidence may be collapsed, but it remains part of the report.
- A proposed fix is displayed only when the recorded evidence supports it. Insufficient evidence produces no invented fix.
- WCAG references may provide context for an evidence-backed finding. They must not be presented as a conformance confirmation or general accessibility conclusion.
- Comparison runs use the same assessment settings for the original and agent-updated versions. Developer-configured consistency levels determine the number of assessments per version: Low one, Medium two, High three; Low is the default.
- Comparisons show every run, per-version scores and metrics, score and metric changes, coverage context, averages, ranges, evidence differences, and mixed or inconclusive results.
- Representative samples are explicitly labeled `Representative sample — not live assessment`. Live Journey-and-Evidence output replaces sample values while preserving the report and comparison contract.
- The current report and comparison spec does not define the Journey-and-Evidence evidence vocabulary or record shape. Those arrive through the separate map and later integration handoff.

## Testing Decisions

- Tests should verify externally visible behavior and evidence presentation, not implementation structure.
- The highest useful seam is setup configuration flowing into a report and then into an original-versus-updated comparison.
- Setup coverage should include valid controlled targets, rejected targets, no-goal whole-site mode, free-text goal mode, unsupported goals, default simulation mode, and comparison settings.
- Report coverage should include every representative sample state, the score calculation, visible passed and attempted counts, metric presentation, explanation and evidence references, WCAG reference wording, proposed-fix omission when evidence is insufficient, and agent-failure presentation.
- Comparison coverage should include Low, Medium, and High consistency levels; identical settings on both versions; every-run visibility; averages and ranges; score and metric deltas; inconclusive and agent-failed runs; and mixed-result labeling.
- Accessibility coverage should verify labeled inputs, keyboard navigation, visible focus, understandable validation errors, and readable report order.
- No test should treat sample values as live browser evidence or require Journey-and-Evidence implementation details that are outside this map.

## Out of Scope

- Browser keyboard execution, site traversal, planner behavior, evidence capture, barrier detection, recovery, run persistence, and controlled-site implementation.
- The Journey-and-Evidence evidence vocabulary and record shape beyond the shared product information this report consumes.
- The later integration handoff that connects live journey output to this report and comparison.
- Remote sites, additional interaction modes, a full accessibility or WCAG conformance claim, axe findings, live trace streaming, databases, orbital visuals, large dashboards, and showcase infrastructure.
- Any score presented as a general accessibility grade or WCAG conformance score.
- A separate agent-fix implementation; this spec only compares the original site with a later agent-updated version when one exists.

## Further Notes

- The contact-form-only MVP rules were superseded by the resolved Wayfinder decisions for this report-and-comparison spec. The current boundary is whole-site by default or goal-focused when a goal is supplied.
- The report should describe itself as evidence for the configured keyboard assessment, not as proof that the whole site is accessible.
- The four representative sample states are planning inputs: whole-site, goal-focused, original-versus-updated improvement, and mixed or incomplete comparison. Every sample must be visibly marked as non-live.
- This spec is intentionally limited to the `REPORT_AND_COMPARISON` map. It must be implemented independently of the Journey and Evidence track and connected only during the later integration handoff.
