# 04 — Run whole-site and free-text goal assessments

**What to build:** The same Journey & Evidence boundary supports a whole-site assessment when no goal is supplied and a goal-focused assessment when a free-text goal is supplied. It tracks declared coverage or goal progress, refuses to silently reinterpret unsupported goals, and continues after website action failures where possible.

**Blocked by:** 02 — Complete the fixed contact-form goal with redacted evidence

**Status:** ready-for-agent

- [ ] A no-goal run records whole-site coverage progress and can complete only when its declared coverage is complete and honestly reported.
- [ ] A supplied free-text goal is carried into planner context, progress observations, and the durable run record.
- [ ] The contact-form goal continues to use the “Message sent” success condition and the controlled Submit behavior.
- [ ] Unsupported or unsafe goals are reported without silent reinterpretation.
- [ ] Website action failures are recorded while the run continues the declared goal or whole-site coverage where possible.
