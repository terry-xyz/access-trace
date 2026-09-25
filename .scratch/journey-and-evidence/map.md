# Journey and Evidence Map

Label: wayfinder:map  
Assignment: JOURNEY_AND_EVIDENCE  
Status: open

## Destination

Reach a handoff-ready product decision set for the Journey & Evidence track: one controlled local demo site can support a whole-site keyboard assessment when no goal is supplied, or a goal-focused keyboard assessment when a free-text goal is supplied, with bounded evidence and truthful terminal outcomes that the report track can consume.

This map produces decisions for a later `to-spec` pass, not implementation deliverables.

## Notes

- Domain: local-first keyboard accessibility evidence for one controlled local demo site.
- Shared configuration contract imported from [Define the supported run-configuration validation boundary](https://github.com/terry-xyz/access-trace/blob/report-and-comparison/.scratch/report-and-comparison/issues/01-run-configuration-validation.md): no goal means a whole-site keyboard assessment; a supplied free-text goal means a goal-focused keyboard assessment; unsupported goals are not silently reinterpreted; the target remains the controlled local site and its broken/fixed versions; comparison settings are reused identically on both versions.
- Shared product contract: interaction is keyboard-only; the autonomous Codex agent plans actions; `simulationMode` is enabled by default and is carried through the run; terminal states are `COMPLETED`, `BLOCKED`, and `INCONCLUSIVE`; the report may compute transparent assessment scores and show named metrics or WCAG references as context, but no result claims full conformance or general accessibility.
- The contact-form journey remains the canonical focused example: when the supplied goal is `Submit the contact form`, the visible success condition is “Message sent” and the controlled broken/fixed Submit barrier applies. That condition is not the universal whole-site success condition.
- Canonical terms: an **assessment scope** is whole-site or goal-focused; a **run** is one isolated attempt; an **observation** is bounded page and browser evidence captured after a settled action; **goal progress** is observable progress toward a supplied goal; **coverage** is the declared whole-site assessment progress; a **stopping point** is the final meaningful focus/progress state; a **repeatable keyboard barrier** is a stopping condition supported by repeated unchanged evidence and failed relevant recovery.
- Shared dependencies with `REPORT_AND_COMPARISON`: assessment scope, goal, simulation context, terminal-state meanings, redaction rule, evidence references, coverage/progress context, and comparison settings must be consumed unchanged. The second map owns run-configuration UX, terminal-report presentation, score and metric presentation, WCAG-reference context, explanation/proposed-fix presentation, and configurable comparison consistency; it must not redefine Journey evidence.
- Handoff condition: after this map is resolved, its `to-spec` output must expose representative whole-site and goal-focused evidence, including completed, blocked, and inconclusive outcomes, without requiring the report track to know journey implementation details. Integration is a later handoff after both maps have produced specs.

## Decisions so far

<!-- Open child tickets live under .scratch/journey-and-evidence/issues/. -->

- [Canonical assessment completion for whole-site and goal-focused journeys](issues/01-canonical-success-condition.md) — no goal completes when declared whole-site coverage is completed and reported honestly; a supplied goal defines goal-focused completion, with “Message sent” remaining the contact-form goal’s local success signal.
- [One controlled barrier for matching broken and fixed contact forms](issues/02-controlled-barrier-choice.md) — for the contact-form goal, Submit stays reachable in both versions, but keyboard activation is inert in the broken version and reaches “Message sent” in the fixed version.
- [Evidence threshold for BLOCKED versus INCONCLUSIVE](issues/03-blocked-vs-inconclusive-evidence.md) — `BLOCKED` requires a repeated relevant stopping point, failed permitted recovery/activation, unchanged scope progress, and absent success or coverage completion; inconsistent or changing evidence remains `INCONCLUSIVE`.
- [Redacted form-input evidence boundary](issues/04-bounded-run-and-evidence-handoff.md) — retain only field identity, focus relationship, character counts, accepted/validation state, and redacted screenshots; never retain raw typed text, clipboard contents, unrestricted source, or input-bearing logs.

## Not yet specified

- The post-spec integration handoff that connects real journey records to the report and comparison surfaces; it is intentionally deferred until both workstream specs exist.
- Any cross-track wiring choices that require seeing both representative implementations; they must not become implementation decisions in this map.
- The exact report-owned named metric definitions and score presentation; Journey supplies bounded evidence and coverage/progress context, while Report & Comparison owns the score contract.

## Out of scope

- The `REPORT_AND_COMPARISON` map: run-configuration UX, plain-language explanation presentation, confidence and evidence-reference presentation, score and named-metric presentation, WCAG-reference context, and Low/Medium/High original-versus-updated comparison consistency.
- The later integration map and any redesign of the shared product contract.
- Arbitrary remote sites, additional demo sites, non-keyboard interaction modes, general accessibility or WCAG conformance claims, a score presented as a general accessibility grade, axe findings, live trace streaming, orbital visuals, large dashboards, databases, and showcase infrastructure.
