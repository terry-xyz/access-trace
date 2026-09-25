# 03 — Classify the broken contact-form barrier

**What to build:** Given the broken controlled site and the goal `Submit the contact form`, a Journey & Evidence run can demonstrate the repeatable keyboard activation barrier and produce a truthful `BLOCKED` result with the evidence needed to explain where progress stopped.

**Blocked by:** 02 — Complete the fixed contact-form goal with redacted evidence

**Status:** ready-for-agent

- [ ] The run reaches the same semantic Submit focus state used by the fixed journey.
- [ ] Both `Enter` and `Space` are attempted while Submit is focused, and neither changes the success state or goal progress.
- [ ] Recovery includes `Tab` and `Shift+Tab`, with `Escape` when a dialog or overlay is present.
- [ ] `BLOCKED` is emitted only after the stopping point recurs with unchanged progress and absent “Message sent”.
- [ ] Whole-page wrapping, an escapable dialog, generic no-progress, and timeout do not automatically become `BLOCKED`.
