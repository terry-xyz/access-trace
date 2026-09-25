# Define representative sample results and the live-data handoff

Type: prototype
Status: resolved
Blocked by: 02, 03

Part of: [Report and Comparison](../map.md)

## Question

Which representative result states must be available before real browser output exists, and how must the product distinguish those samples from live evidence?

Create a small concrete set of representative report and comparison states that exercises the product contract, including a whole-site result, a goal-focused result, an agent-updated comparison, and the inconclusive or inconsistent cases needed to prove honest handling. Use the set to decide:

- which evidence references, explanations, proposed-fix behavior, and confidence levels are visible in each state;
- how the overall score, named metric values, and WCAG references are shown without implying conformance;
- how sample data is labeled so it cannot be mistaken for a real run;
- what the later Journey and Evidence handoff must replace or preserve; and
- how the report remains truthful when a real run has missing evidence or a different result.

The sample set is a planning aid for this track, not a substitute for the later repeated browser runs and not a new demo or showcase scope.

## Answer

Before real browser output exists, the report track uses four clearly labeled representative states:

1. A whole-site assessment with full declared coverage, a score, passed and failed website checks, evidence-backed findings, WCAG references, and a supported proposed fix.
2. A goal-focused assessment where a website action fails but the agent continues, the goal eventually completes, and the score reflects the failed action.
3. An original-versus-agent-updated comparison showing both scores, the score change, each metric change, both reports, and their evidence, labeled `Improved` when the evidence supports that result.
4. A mixed or incomplete comparison showing all runs, score and coverage context, metric changes in both directions, and any agent failure, without inventing a proposed fix when evidence is insufficient.

Every representative state is visibly labeled `Representative sample — not live assessment`. Real Journey and Evidence output replaces the sample values while preserving the report and comparison reading contract. The sample set is not a separate demo or showcase.

The ticket is resolved.
