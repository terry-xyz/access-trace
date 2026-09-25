# Choose the terminal-report reading contract

Type: prototype
Status: resolved

Part of: [Report and Comparison](../map.md)

## Question

What information hierarchy and presentation behavior let a developer understand one terminal result truthfully and quickly?

Create a low-fidelity report outline or equivalent concrete artifact and use it to settle the product-level reading contract. It must account for completed, blocked, and inconclusive outcomes and make clear how the report presents:

- terminal status and whether the assessment or supplied goal completed;
- ordered redacted action evidence, focus and stopping-point evidence, stopping screenshot, warnings, and recovery evidence;
- the plain-language explanation, observed stopping point when applicable, evidence references, confidence, and evidence-backed proposed fix;
- the overall assessment score, each named metric value, and any relevant WCAG references, without presenting either as proof of full conformance;
- target, assessment scope (whole-site or goal-focused), goal when supplied, simulation mode, duration, interaction count, saved run-record link, and the limitation that the result describes only this keyboard assessment; and
- insufficient evidence, omitted fix suggestions, and agent failures when they explain the result; browser and other tool lifecycle warnings are omitted.

Do not decide component structures, visual styling systems, or implementation mechanisms. The artifact is only to settle what the report must foreground, what must remain visibly available as supporting evidence, and how it avoids implying a general accessibility or WCAG conclusion.

## Answer

Use an outcome-first report. The top of the report shows the terminal result, whether the whole-site assessment or supplied goal completed, the overall score, and the key metric values. The score is always shown as:

> passed website checks ÷ attempted website checks × 100

The report then presents the plain-English explanation, followed by the supporting evidence on the same readable page: ordered actions, focus and stopping-point observations, screenshots, recovery evidence, and relevant agent failures. Long evidence may be collapsible, but it must remain part of the same report rather than moving to a separate screen.

The report includes the target, assessment scope, supplied goal, simulation mode, duration, interaction count, saved run-record link, coverage context, confidence, and the limitation that the result describes only this keyboard assessment. It shows relevant WCAG references beside evidence-backed findings, explicitly as context and never as proof of conformance.

Website failures count in the score. The agent must continue attempting all actions toward a supplied goal, or continue checking the whole site when no goal is supplied, even after website failures. Agent failures are shown separately but do not change the score. Browser and other non-agent tool failures are omitted and do not change the score. Proposed fixes appear only when supported by recorded evidence.

The ticket is resolved.
