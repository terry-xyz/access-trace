# One controlled barrier for matching broken and fixed contact forms

Parent map: `../map.md`  
Type: grilling  
Status: resolved  
Blocked by: —

## Question

Which single keyboard behavior should differ between the broken and fixed versions so the barrier is unmistakable, repeatable, observable with the bounded evidence surface, and meaningfully comparable while every other task and success condition remains the same?

Choose the product behavior, not its implementation technique. The decision must make it possible to produce one reliable blocked broken result and one reliable completed fixed result without turning ordinary page wrapping, an escapable dialog, or a generic timeout into a barrier.

## Answer

Keep the Submit control reachable and focusable in both versions. In the broken version, pressing `Enter` or `Space` while Submit is focused leaves the success condition unmet and produces no progress. In the fixed version, the same keyboard activation reaches the visible **“Message sent”** confirmation.

This isolates one keyboard-activation barrier, gives the journey a clear stopping point at the focused Submit control, and keeps the two demo experiences meaningfully comparable without treating ordinary focus wrapping, an escapable dialog, or a timeout as the barrier.

## Cross-map revision

This remains the canonical barrier for the goal-focused `Submit the contact form` journey. The broader whole-site assessment may collect other keyboard evidence, but it must preserve this controlled contact-form contrast when that goal is supplied and must not treat the Submit-specific behavior as the universal whole-site completion rule.
