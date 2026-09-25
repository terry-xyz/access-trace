# Redacted form-input evidence boundary

Parent map: `../map.md`  
Type: grilling  
Status: resolved  
Blocked by: 03

## Question

What non-value metadata is sufficient to prove that the keyboard journey populated and traversed the contact-form fields while preserving the rule that raw typed values are never retained?

Choose the evidence boundary for field-level redaction metadata—such as character counts, accepted-input or validation state, and the relationship to focus observations—without designing a storage schema. It must support the already-defined ordered actions, focus evidence, warnings, recovery results, stopping screenshot, timestamps, duration, interaction count, terminal state, and linkable run record. It must carry `simulationMode` unchanged and give the report track a stable, truthful handoff without exposing or reconstructing fictional typed values.

## Answer

Retain only non-value metadata: each field’s semantic identity, its relationship to focus observations, the character count for each bounded text-entry action, and whether the input was accepted with any observed validation state. Ordered keyboard actions may be retained, but never their raw typed text.

Stopping screenshots are retained only when editable values are absent or visibly redacted before persistence. Raw values, clipboard contents, unrestricted DOM or source content, and browser logs containing input are never retained. This evidence boundary proves that the journey populated and traversed the fields while preserving `simulationMode` and the rest of the run record unchanged for the report track.

## Cross-map revision

The same redaction boundary applies to whole-site and goal-focused assessments. Contact-form field metadata remains the concrete example, while any other bounded text entry in a supplied goal or whole-site check may retain only equivalent non-value metadata and redacted visual evidence.
