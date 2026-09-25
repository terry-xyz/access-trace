# 01 — Launch the controlled local assessment target

**What to build:** A developer can start a fresh Journey & Evidence run against either matching version of the controlled local site. The run carries the assessment scope, optional goal, and `simulationMode`, and the site exposes the fictional contact form needed for the focused goal. The fixed version allows keyboard activation of Submit; the broken version keeps Submit reachable and focusable but leaves the state unchanged for `Enter` and `Space`.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] Both local versions contain the same fictional name, email, message, Submit control, and visible “Message sent” confirmation.
- [ ] A fresh run can target either version while preserving the assessment scope, optional goal, and `simulationMode` context.
- [ ] Submit is keyboard reachable in both versions; the fixed version can activate it and the broken version does not respond to `Enter` or `Space`.
- [ ] The run records a first bounded observation without exposing raw typed values or unrestricted page content.
