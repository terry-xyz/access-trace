# Journey and Evidence Specification

Parent map: `map.md`  
Assignment: `JOURNEY_AND_EVIDENCE`  
Status: ready-for-agent  
Label: ready-for-agent

This specification covers only the Journey & Evidence workstream. It incorporates the updated shared MVP contract from the Report & Comparison workstream and leaves report presentation, scoring, comparison presentation, and the later integration handoff to that workstream.

## Problem Statement

Developers need trustworthy evidence from a local-first keyboard assessment. The assessment must support a whole-site run when no goal is supplied and a goal-focused run when a developer supplies a free-text goal. It must show what happened in the browser, distinguish a repeatable keyboard barrier from an inconclusive failure, and preserve enough redacted evidence for another part of the product to explain and compare the result.

The product must remain honest about its limits. An assessment of one controlled local site cannot establish general accessibility or WCAG conformance. A transparent assessment score may be presented downstream, but it must not be described as a general accessibility grade or conformance score. Typed form values must not be persisted merely to make the evidence persuasive.

## Solution

Provide one local-first Journey & Evidence run against one controlled local demo site and its matching broken and fixed versions. With no goal, the autonomous agent performs a whole-site keyboard assessment. With a supplied free-text goal, it performs a goal-focused keyboard assessment; it must not silently reinterpret a goal it cannot safely assess.

Every run carries the target, assessment scope, optional goal, `simulationMode` enabled by default, and keyboard-only interaction profile. The autonomous Codex agent chooses only permitted keyboard actions or bounded plain-text entry from bounded observations. The browser interaction surface exposes no mouse, arbitrary JavaScript, selectors, credentials, shell commands, unrestricted page source, or raw typed values to the agent.

The controlled contact form remains the canonical focused goal. When the supplied goal is `Submit the contact form`, the visible success condition is **“Message sent”**. Submit is reachable and focusable in both versions; keyboard activation reaches the confirmation in the fixed version and is inert in the broken version. The same journey evidence rules generalize to other goal-focused checks and whole-site coverage without treating “Message sent” as the universal whole-site success condition.

After every settled action, the journey records a bounded observation and keeps the evidence needed to classify the run. Website action failures are recorded and the agent continues the declared goal or whole-site coverage where possible. Browser, planner, or repeated action-delivery failures remain distinct and can make the result `INCONCLUSIVE`. The resulting durable record is the evidence handoff for the separate report and comparison experience.

## User Stories

1. As a developer, I want to run an assessment with no goal, so that the agent checks the declared coverage of the whole controlled local site.

2. As a developer, I want to enter a free-text goal, so that the agent can assess a specific outcome I care about.

3. As a developer, I want an unsupported or unsafe goal explained clearly, so that the agent does not silently reinterpret my request or claim evidence it cannot produce.

4. As a developer, I want to provide or confirm the target URL for the controlled local site, so that the assessment runs against the intended local target.

5. As a developer, I want invalid, remote, off-loopback, or unrecognized targets prevented from starting an assessment, so that the evidence remains within the controlled local boundary.

6. As a developer, I want `simulationMode` enabled by default and carried through the whole run, so that the local demonstration is clearly distinguished from a real-world transaction.

7. As a developer, I want the same scope, goal-or-no-goal choice, browser conditions, success rules, and simulation mode reused for both versions in a comparison, so that the later comparison is fair.

8. As a developer, I want the assessment to use actual browser keyboard interaction, so that the result reflects keyboard behavior rather than a synthetic claim about the page.

9. As a developer, I want the interaction surface restricted to `Tab`, `Shift+Tab`, `Enter`, `Space`, `ArrowLeft`, `ArrowRight`, `ArrowUp`, `ArrowDown`, `Escape`, and bounded plain-text typing, so that the result cannot be achieved through hidden pointer or automation capabilities.

10. As a developer, I want the autonomous journey agent to choose actions from bounded evidence, so that it can adapt to the current page without receiving unrestricted page content.

11. As a developer, I want page evidence treated as untrusted data, so that text on the target page cannot instruct the agent to break its interaction or evidence boundaries.

12. As a developer, I want the planner to receive the assessment scope, optional goal, simulation context, current URL and title, bounded screenshot and accessibility evidence when available, semantic focus facts, progress, coverage, warnings, and bounded recent history, so that every decision is grounded in permitted context.

13. As a developer, I want an invalid action decision retried once against the same observation, so that one malformed decision does not immediately misclassify a run.

14. As a developer, I want a planner timeout retried once and then classified as inconclusive, so that planner failure is bounded and truthful.

15. As a developer, I want a failed browser action to trigger a fresh observation and repeated action-delivery failure to end the run inconclusively, so that an unobserved browser failure is not called a keyboard barrier.

16. As a developer, I want website action failures recorded while the agent continues the declared goal or whole-site coverage where possible, so that website problems contribute evidence rather than silently ending the assessment.

17. As a developer, I want agent failures shown as agent evidence separate from website failures, so that a low-quality assessment is not mistaken for a website finding.

18. As a developer, I want each run to use a fresh isolated browser session, so that prior focus, page state, dialogs, or navigation cannot contaminate the evidence.

19. As a developer, I want the journey to record an observation after every settled action, so that the ordered action history can be checked against the resulting browser state.

20. As a developer, I want each observation to include the settled URL and title, so that navigation remains bounded to the intended local target.

21. As a developer, I want each observation to include semantic focus facts—focused role, accessible name, tag, and stable focus facts—so that stopping points and barriers can be described precisely.

22. As a developer, I want each observation to include success state, goal progress when a goal is supplied, and whole-site coverage when no goal is supplied, so that completion and lack of progress are evidence-backed.

23. As a developer, I want warnings and browser lifecycle events recorded, so that dialogs, popups, crashes, closed pages, and off-loopback redirects are visible in the final result.

24. As a developer, I want the fixed and broken versions to contain the same fictional site content and contact form, so that evidence compares the intended behavioral change rather than unrelated site changes.

25. As a developer, I want the fixed contact-form goal to reach and activate Submit with the keyboard and verify “Message sent”, so that it provides a reliable completed focused-goal result.

26. As a developer, I want the broken contact-form goal to keep Submit reachable and focusable but make `Enter` and `Space` inert there, so that its barrier is repeatable and has a clear stopping point.

27. As a developer, I want a goal-focused run marked `COMPLETED` only when the supplied goal’s success is locally verified after permitted keyboard progress, so that an agent claim alone can never produce success.

28. As a developer, I want a whole-site run marked `COMPLETED` only when its declared coverage completes and the evidence reports that coverage honestly, so that whole-site completion is not confused with one goal’s success signal.

29. As a developer, I want a run marked `BLOCKED` only when a relevant semantic stopping point recurs, permitted recovery or activation fails, scope progress is unchanged, and the intended goal or whole-site coverage remains incomplete, so that a likely barrier is supported by repeated evidence.

30. As a developer, I want the contact-form barrier to require the same Submit focus state twice, failed `Enter` and `Space` activation, unchanged progress, and a relevant recovery pass, so that the canonical broken result is especially clear.

31. As a developer, I want recovery to include `Tab` and `Shift+Tab`, and `Escape` when a dialog or overlay is present, so that focus and modal recovery are tested before declaring a barrier.

32. As a developer, I want whole-page wrapping, an escapable dialog, and generic no-progress to avoid automatic `BLOCKED` classification, so that ordinary navigation behavior is not overinterpreted.

33. As a developer, I want timeout, browser failure, planner failure, unsupported goal, missing evidence, or inconsistent recovery to produce `INCONCLUSIVE`, so that uncertainty is reported honestly.

34. As a developer, I want ordered keyboard actions and bounded observations retained for each run, so that the result can be independently understood from evidence rather than from a summary alone.

35. As a developer, I want field-level semantic identity, focus relationship, character counts, accepted-input state, and observed validation state retained without raw values, so that evidence proves form progress without exposing typed content.

36. As a developer, I want stopping screenshots retained only when editable values are absent or visibly redacted, so that visual evidence cannot leak or reconstruct typed values.

37. As a developer, I want raw typed text, clipboard contents, unrestricted DOM or source content, and input-bearing browser logs excluded from durable evidence, so that simulation mode does not weaken privacy or redaction.

38. As a developer, I want every run record to carry target, assessment scope, optional goal, simulation mode, timestamps, duration, interaction count, ordered redacted actions, focus observations, coverage or goal progress, stopping point, stopping screenshot reference, warnings, recovery evidence, terminal state, agent-failure evidence, and downstream explanation/proposed-fix handoff data when supported, so that the report track receives a complete evidence package.

39. As a report-track agent, I want representative whole-site and goal-focused records covering completed, blocked, inconclusive, incomplete, and agent-failed states, so that report and comparison work can proceed before real browser output is connected.

40. As a developer, I want the journey handoff to describe its result as evidence for the configured keyboard assessment, so that downstream presentation cannot turn it into a general accessibility or WCAG conclusion.

## Implementation Decisions

- The implementation is limited to the Journey & Evidence workstream. It owns the controlled demo experiences, real browser keyboard execution, bounded journey planning context, observation capture, coverage and goal-progress tracking, barrier determination, recovery and warning evidence, redaction, and durable run-record handoff.

- The current MVP has two assessment scopes: whole-site when no goal is supplied, and goal-focused when a free-text goal is supplied. A goal defines the intended success for that run; an unsupported goal is not silently reinterpreted.

- The target remains the controlled local site and its matching broken/fixed versions. Invalid, remote, off-loopback, or unrecognized targets must not begin an assessment.

- The shared contact-form example remains a focused goal contract. For `Submit the contact form`, the fixed version reaches the visible “Message sent” confirmation after keyboard-only progress to and activation of Submit. The broken version keeps Submit reachable and focusable but leaves the state unchanged for both `Enter` and `Space`.

- “Message sent” is not the universal whole-site success condition. A goal-focused run verifies the supplied goal’s observable success; a whole-site run verifies completion of its declared coverage and reports that coverage honestly.

- `simulationMode` is a first-class run parameter, enabled by default, present in planner context and durable evidence, and passed unchanged to downstream report and comparison work. It means the local target is a simulation and no real-world transaction is intended; it never relaxes validation, confirmation, redaction, or failure handling.

- Each run starts in a fresh isolated browser session and uses real keyboard input. The interaction surface is limited to the permitted keys and bounded plain-text typing. No pointer action or unrestricted browser capability is part of the journey contract.

- The autonomous planner receives only the assessment scope, optional goal, simulation context, current URL and title, bounded screenshot and accessibility evidence when available, semantic focus facts, goal progress or whole-site coverage, warnings, and bounded recent action history. Page evidence is untrusted data.

- Planner and action handling distinguishes website failures from agent or browser failures. Invalid decisions are retried once against the same observation; a planner timeout is retried once; browser action failures trigger re-observation; repeated action-delivery failure ends inconclusively. Website action failures are recorded and the agent continues the declared goal or whole-site coverage where possible.

- The journey records a settled observation after every action. Observations cover URL, title, semantic focus, goal success or coverage state, task progress, warnings, lifecycle events, dialogs, popups, crashes, closed pages, and off-loopback redirects without exposing unrestricted page content.

- Classification is evidence-based:

  - `COMPLETED` means a goal-focused run has locally verified the supplied goal’s success, or a whole-site run has completed its declared coverage and reported it honestly.
  - `BLOCKED` requires a repeated relevant semantic stopping point, absent goal success or incomplete whole-site coverage, unchanged scope progress, failed permitted recovery or activation, and evidence that supports a likely keyboard barrier. For the contact-form goal, this specifically requires the same Submit focus state twice, failed `Enter` and `Space` activation, and the relevant recovery pass.
  - `INCONCLUSIVE` covers missing or inconsistent evidence, timeout, planner or browser failure, unsupported goal, and recovery that changes the meaningful state. Whole-page wrapping, an escapable dialog, and generic no-progress do not automatically qualify as `BLOCKED`.

- The durable run record retains run parameters, assessment scope, optional goal, simulation mode, timestamps, duration, interaction count, ordered redacted actions, focus observations, coverage or goal progress, stopping point, stopping screenshot reference, warnings, recovery evidence, terminal state, agent-failure evidence, and downstream explanation/proposed-fix handoff data when supported.

- Redaction is a product boundary, not an optional presentation feature. Retain field semantic identity, focus relationship, character counts, accepted-input state, and observed validation state; never retain raw typed text, clipboard contents, unrestricted DOM or source content, or input-bearing browser logs. Stopping screenshots must omit or visibly redact editable values before persistence.

- The Journey & Evidence handoff exposes bounded action evidence, focus and stopping-point evidence, screenshots, recovery and warning evidence, coverage or goal progress, and terminal context. The Report & Comparison workstream owns transparent overall score and named-metric presentation, WCAG-reference context, explanation/proposed-fix presentation, and Low/Medium/High comparison consistency.

- No file layout, framework, dependency, persistence technology, browser API, request/response shape, selector, component structure, score implementation, or test architecture is prescribed by this specification.

## Testing Decisions

- Test the highest available seam: one black-box end-to-end assessment lifecycle from canonical run parameters through real keyboard interaction and bounded observation to the durable redacted run record. Do not test internal module structure or implementation details.

- The fixed contact-form goal must produce an externally observable `COMPLETED` result whose evidence shows progress through the fields, Submit focus, allowed activation, and the visible “Message sent” confirmation.

- The broken contact-form goal must produce an externally observable `BLOCKED` result whose evidence shows repeated semantic Submit focus, failed `Enter` and `Space` activation, unchanged goal progress, missing confirmation, and the relevant recovery pass.

- Whole-site coverage must exercise a run without a goal and verify that the journey records coverage progress, continues after website action failures where possible, and reports completion or incompleteness without inventing a goal-specific success signal.

- Goal-focused coverage must exercise a supplied free-text goal, verify that progress and success are tied to that goal, and verify that unsupported goals are not silently reinterpreted.

- Failure-path tests must produce `INCONCLUSIVE` for planner timeout after its permitted retry, repeated action-delivery failure, browser or lifecycle failure, off-loopback navigation, unsupported goal, missing evidence, and inconsistent recovery. Tests must verify that none of these are silently converted to `BLOCKED`.

- Evidence tests must verify an observation after every settled action, ordered redacted actions, focus facts, coverage or goal progress, stopping point, warnings, recovery evidence, terminal state, agent-failure evidence, and stopping screenshot reference.

- Redaction tests must verify that raw typed values do not appear in the run record, action history, screenshot reference set, clipboard-derived evidence, unrestricted page evidence, or input-bearing browser logs. They should verify that character counts and accepted/validation metadata remain available.

- Capability-boundary tests must verify that the journey can assess the supported scopes using only the permitted keyboard actions and bounded typing, without pointer actions, arbitrary scripts, selectors, credentials, shell commands, or unrestricted DOM content.

- Browser lifecycle tests should cover dialogs, popups, crashes, closed pages, and off-loopback redirects as observable warnings or inconclusive outcomes according to the evidence available.

- Prior art: the repository currently contains no implementation or test suite. The first tests should therefore establish external assessment behavior at the single lifecycle seam rather than mirror any imagined internal architecture.

## Out of Scope

- The Report & Comparison workstream’s run-configuration interface and validation presentation.
- Plain-language explanation generation and presentation, evidence-reference presentation, confidence presentation, proposed-fix presentation, transparent score and named-metric presentation, WCAG-reference context, and Low/Medium/High original-versus-updated comparison presentation.
- The later integration handoff that connects both independently implemented specs.
- Claims of full accessibility or WCAG conformance, a score presented as a general accessibility grade, or unsupported AI conclusions.
- Any remote website, arbitrary target, additional controlled demo site, real-world transaction, or task scope beyond whole-site or supplied-goal assessment of the controlled local site.
- Mouse, pointer, touch, screen-reader, voice, or other disability and interaction modes.
- Axe findings, live trace streaming, orbital or ornamental visuals, large multi-screen dashboards, demo-only presentation layers, databases, and showcase infrastructure.
- Technical choices such as frameworks, package manifests, dependency versions, file structures, browser handles, selectors, API paths, request or response schemas, component structures, persistence schemas, score algorithms, and test architecture.

## Further Notes

- The separate Report & Comparison spec must consume the shared terms and decisions in this document: whole-site versus goal-focused assessment scope, optional goal, keyboard-only interaction, `simulationMode`, `COMPLETED`, `BLOCKED`, `INCONCLUSIVE`, the contact-form “Message sent” success signal when that goal is supplied, the redaction boundary, coverage or goal-progress evidence, and evidence references.

- The Report & Comparison workstream may begin with representative whole-site and goal-focused sample records. Real Journey & Evidence output later replaces the sample values through the same evidence contract.

- Comparison consistency is owned by Report & Comparison: Low is one assessment per version, Medium is two, and High is three, with Low as the default. The Journey track must preserve enough evidence for those repeated assessments without changing its run contract.

- The first milestone remains one reliable completed fixed result, one reliable blocked broken result for the contact-form goal, and enough truthful evidence for downstream explanation. Whole-site and broader goal-focused support must not weaken that demonstration.

- Integration begins only after both workstream specs exist and representative work is available. Integration must connect real Journey evidence to the report and comparison surfaces without redesigning the shared product contract or adding new scope.
