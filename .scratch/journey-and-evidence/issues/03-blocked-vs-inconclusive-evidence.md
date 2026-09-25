# Evidence threshold for BLOCKED versus INCONCLUSIVE

Parent map: `../map.md`  
Type: grilling  
Status: resolved  
Blocked by: 01, 02

## Question

What repeatability threshold and relevant recovery sequence must the journey observe before classifying a whole-site or goal-focused run as `BLOCKED`, and what evidence requires `INCONCLUSIVE` instead?

The decision must make the relevant stopping point, unchanged scope progress, unmet goal success or incomplete whole-site coverage, action failures, and recovery attempts legible in durable evidence. It must explicitly account for `Tab`, `Shift+Tab`, and `Escape` when relevant, while excluding whole-page wrapping, an escapable dialog, timeout, browser failure, planner failure, unsupported goals, and insufficient evidence from automatic `BLOCKED` classification.

## Answer

Apply the same evidence discipline to both assessment scopes. Classify a run as `BLOCKED` only when all of the following are observed:

- The same relevant semantic stopping point recurs after recovery. For the contact-form goal, this is the same semantic Submit focus state observed twice.
- The intended goal success remains absent, or the declared whole-site coverage remains incomplete.
- Scope progress is unchanged.
- The relevant permitted activation or recovery actions fail to change the meaningful state. For the contact-form goal, both `Enter` and `Space` are attempted while Submit is focused and neither changes the state.
- A relevant recovery pass is attempted with `Tab` and `Shift+Tab`; `Escape` is included when a dialog or overlay is present.

Use `INCONCLUSIVE` for missing or inconsistent evidence, timeout, planner or browser failure, unsupported goals, or recovery that changes the meaningful state. Whole-page wrapping, an escapable dialog, and generic no-progress do not qualify automatically as `BLOCKED`.
