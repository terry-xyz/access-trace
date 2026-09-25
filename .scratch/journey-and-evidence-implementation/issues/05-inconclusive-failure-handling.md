# 05 — Handle planner, browser, and lifecycle failures as inconclusive

**What to build:** The journey handles invalid planner choices, planner timeouts, repeated action-delivery failures, and browser lifecycle problems without inventing a keyboard barrier. It records the available warnings and keeps agent failures distinct from website failures before producing `INCONCLUSIVE` when reliable assessment evidence is unavailable.

**Blocked by:** 02 — Complete the fixed contact-form goal with redacted evidence

**Status:** ready-for-agent

- [ ] An invalid action decision is retried once against the same observation.
- [ ] A planner timeout is retried once and then ends the run inconclusively if it persists.
- [ ] Action-delivery failure triggers re-observation, and repeated failure ends the run inconclusively.
- [ ] Dialogs, popups, crashes, closed pages, and off-loopback redirects are captured as warnings or inconclusive lifecycle outcomes according to the evidence available.
- [ ] Agent failures remain distinguishable from website action failures in the resulting evidence.
- [ ] Missing or inconsistent evidence, unsupported goals, and changing recovery state are never silently classified as `BLOCKED`.
