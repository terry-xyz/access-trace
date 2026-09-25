# Canonical assessment completion for whole-site and goal-focused journeys

Parent map: `../map.md`  
Type: grilling  
Status: resolved  
Blocked by: —

## Question

What completion semantics should matching controlled-site versions share so that a goal-focused run verifies the supplied goal while a no-goal run verifies declared whole-site coverage, without relying on an agent claim alone?

The decision must define the observable success or coverage evidence used by Journey & Evidence and the shared handoff consumed by Report & Comparison. It must preserve keyboard-only interaction, `simulationMode`, and the limitation that the result is evidence for the configured keyboard assessment rather than a general accessibility or WCAG conclusion.

## Answer

Use two assessment scopes:

- With no goal supplied, perform a whole-site keyboard assessment. `COMPLETED` means the declared whole-site coverage completed and the evidence reports that coverage honestly; no contact-form confirmation is required as a universal success signal.
- With a free-text goal supplied, perform a goal-focused keyboard assessment. The supplied goal defines the intended success, and an unsupported goal must not be silently reinterpreted.

When the supplied goal is `Submit the contact form`, the focused success condition is a settled local observation of the visible **“Message sent”** confirmation after keyboard-only progress to and activation of Submit. A planner success claim alone is never sufficient.

The same scope, goal-or-no-goal choice, browser conditions, success rules, and `simulationMode` are reused on both sides of a comparison. These completion and coverage semantics are shared dependencies for the report and comparison track.
