# 02 — Complete the fixed contact-form goal with redacted evidence

**What to build:** Given the fixed controlled site and the goal `Submit the contact form`, a real keyboard-only Journey & Evidence run can populate the form, reach and activate Submit, verify the visible “Message sent” confirmation, and produce a durable `COMPLETED` result for downstream reporting.

**Blocked by:** 01 — Launch the controlled local assessment target

**Status:** ready-for-agent

- [ ] The autonomous journey agent chooses only permitted keyboard actions or bounded plain-text typing from bounded, untrusted page evidence.
- [ ] The run uses a fresh isolated browser session and records an observation after every settled action.
- [ ] Completion requires locally observed “Message sent” after keyboard-only progress and Submit activation; an agent claim alone cannot complete the run.
- [ ] The durable result includes ordered redacted actions, focus observations, goal progress, timestamps, duration, interaction count, stopping evidence, and `simulationMode`.
- [ ] Raw typed values, clipboard contents, unrestricted source, and input-bearing logs are not retained.
