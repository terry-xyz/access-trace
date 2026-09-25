# Define the supported run-configuration validation boundary

Type: grilling
Status: resolved

Part of: [Report and Comparison](../map.md)

## Question

What user-facing rules make a run configuration valid, unsupported, or unable to start?

Resolve the product boundary for the setup experience without prescribing implementation details. In particular, decide how the experience should handle:

- the one supported contact-form task versus another task wording;
- the target URL restriction to the controlled local demo site and its broken/fixed versions;
- entering or confirming the visible success condition;
- the default and explicit confirmation of `simulationMode`;
- whether the same validated configuration is required for both sides of a comparison; and
- understandable validation errors that stop an invalid run or comparison before it starts.

The result must preserve the shared contract: unsupported tasks are explained clearly, `simulationMode` is first-class, and simulation mode never weakens validation or failure handling.

## Answer

The run setup supports two assessment modes:

- With no goal, the agent performs a whole-site keyboard assessment of the controlled local site.
- With a goal, the agent performs a goal-focused keyboard assessment. Goals are free text; the agent must not silently reinterpret an unsupported goal, and must report when it cannot safely assess one.

The target remains the controlled local site. An invalid, remote, off-loopback, or unrecognized target must not start a run. A comparison uses the original site and the later agent-produced version of that same site, with the same goal-or-no-goal choice, browser conditions, success rules, and simulation mode.

`simulationMode` remains enabled by default, must be visible in the run context and comparison, and does not weaken validation, evidence handling, or failure handling. A separate contact-form success condition is no longer required: a provided goal defines the intended success; without a goal, completion means the declared whole-site coverage was completed and reported honestly.

The report will include an overall assessment score and transparent values for each named metric. It may reference relevant WCAG criteria alongside evidence-backed findings, but it must not claim full WCAG conformance. Exact metric definitions and score presentation remain for the report and comparison tickets.

The ticket is resolved. The optional goal input is part of the current MVP; it is not deferred to a later feature.
