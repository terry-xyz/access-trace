# Report WCAG Condition Correlations

## Goal

Relate every accessibility condition identified in a completed run's report to a WCAG 2.2 success criterion when the recorded evidence supports that relationship.

## User experience

Each identified condition displays its WCAG 2.2 criterion identifier and short name beside the condition. When the evidence does not support a direct mapping, display “No direct WCAG mapping identified.” The report must not turn a condition mapping into a claim that the page conforms to WCAG.

## Evidence and sources

Use the recorded run evidence to support both the condition and its criterion mapping. The supplied references inform the interpretation:

- Brunel University London, “Web accessibility barriers and their cross-disability impact in eSystems: A scoping review” (2025), for cross-disability barrier context.
- ETSI EN 301 549 V3.2.1 (2021), for the ICT accessibility requirements and its WCAG-aligned web requirements.
- WHO/ITU, “Implementation toolkit for accessible telehealth services” (2024), for telehealth accessibility requirements and context.

These references inform the mapping; they do not substitute for evidence from the assessed run or change WCAG criterion applicability.

## Behavior and boundaries

- Represent condition-to-criterion correlations as structured report data so each condition has its own mapping.
- Use a valid WCAG 2.2 success criterion identifier and name for direct mappings.
- Permit an explicit unmapped result when evidence is insufficient or no direct criterion applies; never force a best guess.
- Keep evidence references connected to the condition they support.
- Present mappings as informative correlations, not a WCAG conformance assessment.
- Retain the existing report's evidence, confidence, and proposed-fix roles.

## Validation

Review representative keyboard, focus, form, and navigation conditions for correct criterion mappings and evidence links. Include a condition with ambiguous or insufficient evidence and confirm it renders as unmapped. Check that the report does not describe the overall page as WCAG-conformant.
