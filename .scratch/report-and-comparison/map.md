# Report and Comparison

## Destination

Produce a handoff-ready product specification for the report-and-comparison track: a developer can configure either a whole-site or goal-focused keyboard assessment, read a truthful report with transparent scores and metrics, and compare an original site with its later agent-produced version using meaningful evidence and clear uncertainty boundaries.

## Notes

This is the second Wayfinder pass for AccessTrace, assigned only to `REPORT_AND_COMPARISON`. The original prompt's contact-form-only MVP constraints were superseded during this map's first decision. The current working contract is a whole-site assessment when no goal is supplied, or a free-text goal-focused assessment when a goal is supplied; it remains keyboard-only and local-first, carries `simulationMode` through every result, and uses WCAG references without claiming full conformance.

Use the established product language: assessment scope, optional goal, simulation mode, terminal state, action evidence, focus observation, stopping point, screenshot evidence, recovery evidence, explanation, proposed fix, confidence, score, metric, WCAG reference, and before/after comparison. Resolve product choices only; leave implementation choices to the later implementation agents.

## Decisions so far

- [Define the supported run-configuration validation boundary](issues/01-run-configuration-validation.md) — Run setup now supports whole-site or free-text goal-focused assessments; comparisons reuse identical settings, with transparent scores and WCAG references but no conformance claim.
- [Choose the terminal-report reading contract](issues/02-terminal-report-reading-contract.md) — Reports lead with outcome and an always-present passed-check score, keep supporting evidence on the same page, show agent failures separately, and use WCAG references without conformance claims.
- [Define honest before-and-after comparison semantics](issues/03-before-after-comparison-semantics.md) — Original and agent-updated versions use the same configurable consistency level, Low by default; comparison shows score and metric changes, every run, averages, ranges, and mixed results.

- [Define representative sample results and the live-data handoff](issues/04-representative-sample-handoff.md) — Four visibly labeled sample states cover whole-site, goal-focused, improved, mixed, incomplete, failed-step, and agent-failure reporting before live data arrives.

## Not yet specified

- The exact report-facing evidence vocabulary and sample record shape will become concrete when the Journey and Evidence map produces its `to-spec` output and representative records.
- The later integration handoff must connect real journey records to this track without changing the shared product contract.
- The final wording for unusual mixed-result comparisons may need a focused review after the original and agent-updated assessments exist.

## Boundary with Journey and Evidence

This map owns run-configuration validation, terminal-report presentation, evidence explanation and proposed-fix presentation, evidence references, confidence, comparison presentation, and representative sample results.

The Journey and Evidence map owns the controlled demo experiences, real browser keyboard interaction, bounded observations, whole-site coverage or goal progress, barrier determination, recovery and warning evidence, stopping screenshots, redacted run records, and the resulting assessment evidence. This map must consume that evidence and must not redesign or duplicate it.

## Shared dependencies

- Both maps use the same whole-site-versus-goal-focused assessment scope, keyboard-only profile, simulation-mode semantics, evidence limits, score boundaries, and WCAG-reference limitation established by the resolved run-configuration decision.
- Report and comparison decisions depend on the Journey and Evidence handoff exposing enough bounded evidence to show coverage or goal progress, identify barriers and stopping points, verify success, reference screenshots, and distinguish insufficient evidence.
- The report track may proceed with representative sample results before real browser output exists, but sample content must be visibly distinguishable from a real run and must be replaceable by the later integration handoff.

## Handoff conditions

The map is ready for its separate `to-spec` pass; all of its decision tickets are resolved. The resulting spec must define, without implementation prescriptions:

- the whole-site and goal-focused run-configuration experience;
- the minimum truthful terminal report and explanation for completed, blocked, and inconclusive outcomes;
- the overall score, named metrics, evidence references, confidence, proposed-fix rules, WCAG references, simulation-mode visibility, and limitation statement;
- the original-versus-agent-updated comparison, its repeated-run protocol, and its inconsistency disclosure; and
- the representative sample states needed to work before real journey output arrives.

Integration is a later handoff after both maps have produced their specs and representative work. It is not a ticket in this map.

## Out of scope

- The Journey and Evidence map's browser, demo-site, planner, evidence-capture, recovery, persistence, and run-execution decisions.
- The later integration handoff and connection of real browser output.
- Remote sites, additional interaction modes, claims of full accessibility or WCAG conformance, axe findings, live trace streaming, databases, orbital visuals, large dashboards, and showcase infrastructure.
