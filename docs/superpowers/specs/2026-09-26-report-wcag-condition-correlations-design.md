# Report WCAG Condition Correlations

## Goal

Relate every accessibility condition identified in a completed run's report to a WCAG 2.2 success criterion when the recorded evidence supports that relationship. When no direct WCAG criterion applies, show a specific related statement from the supplied ETSI, WHO/ITU, or Brunel sources if the evidence supports it.

## User experience

Each identified condition displays its WCAG 2.2 criterion identifier and short name beside the condition. If no direct WCAG criterion applies, display a linked source statement with its type and clause, requirement, or article locator. When neither kind of relationship is supported, display “No direct WCAG or supplied-source mapping identified.” The report must not turn a correlation into a claim of conformance or an official determination that a source requirement is unmet.

## Evidence and sources

Use the recorded run evidence to support both the condition and its criterion mapping. The supplied references inform the interpretation:

- Brunel University London, “Web accessibility barriers and their cross-disability impact in eSystems: A scoping review” (2025), for cross-disability barrier context.
- ETSI EN 301 549 V3.2.1 (2021), for the ICT accessibility requirements and its WCAG-aligned web requirements.
- WHO/ITU, “Implementation toolkit for accessible telehealth services” (2024), for telehealth accessibility requirements and context.

The runtime source catalog contains all 25 numbered WHO/ITU toolkit requirements, three ETSI clauses potentially observable in this assessment, and three barrier examples from the Brunel article. The catalog is a bounded set of paraphrased statements with published links and locators. It is not a full-text search over the PDFs. These references do not substitute for evidence from the assessed run or change WCAG criterion applicability.

## Behavior and boundaries

- Represent condition-to-criterion correlations as structured report data so each condition has its own mapping.
- Use a valid WCAG 2.2 success criterion identifier and name for direct mappings.
- Prioritize a direct WCAG mapping. Use a supplied-source statement only when no direct WCAG criterion applies and the observed condition clearly matches the statement.
- Permit an explicit unmapped result when evidence is insufficient or no direct source applies; never force a best guess.
- Keep evidence references connected to the condition they support.
- Present mappings as informative correlations, not a WCAG conformance assessment.
- Retain the existing report's evidence, confidence, and proposed-fix roles.

## Validation

Review representative keyboard, focus, form, and navigation conditions for correct criterion mappings and evidence links. Include a condition with ambiguous or insufficient evidence and confirm it renders as unmapped. Check that the report does not describe the overall page as WCAG-conformant.
