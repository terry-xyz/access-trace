# Report WCAG Condition Correlations Implementation Plan

**Goal:** Show each evidence-based accessibility condition with a related WCAG 2.2 success criterion, or an explicit unmapped result.

**Architecture:** The reviewer returns bounded condition text, a WCAG criterion ID or null, and evidence IDs for each condition. Python resolves the ID to a canonical W3C name and URL, validates every citation, and projects the safe records into the evidence handoff. The report renders condition text, a criterion link or an unmapped label, and links to the condition's own evidence.

**Sources:** W3C's [WCAG 2.2 Recommendation](https://www.w3.org/TR/WCAG22/) supplies the canonical 86 active success criteria. ETSI EN 301 549 V3.2.1 clause 9 maps web requirements to WCAG 2.1; the overlapping criteria remain applicable in WCAG 2.2. Brunel University's scoping review discusses cross-disability barriers and the limits of treating conformance as the whole accessibility picture. The WHO/ITU telehealth toolkit supplies broader service context, including assistive-device compatibility (requirement 1), contrast (requirement 2), captions (requirement 7), and mobility requirements (13–15). Those broader requirements are context, not automatic WCAG mappings.

**Source fallback:** `access_trace/source_references.py` contains canonical, linked source statements. The reviewer can select one only when it cannot select a direct WCAG criterion. `access_trace/report.py` validates the selected source ID, and `access_trace/evidence.py` validates the full source record again before display. The UI labels WHO/ITU as toolkit requirements, ETSI as standard requirements, and Brunel as research findings. The catalog covers the 25 WHO/ITU requirements, ETSI clauses 5.9, 6.4, and 12.1.1, and three Brunel barrier examples; it is not full PDF retrieval.

## Work items

- [x] Add a static canonical WCAG 2.2 ID, name, and anchor registry in `access_trace/wcag.py`, excluding obsolete 4.1.1.
- [x] Add bounded `conditions` to the review schema and prompt in `access_trace/report.py`. Derive criterion name, URL, and mapped/unmapped status in validation; reject unsupported IDs and unknown evidence locators.
- [x] Preserve safe condition records in `access_trace/evidence.py`. Revalidate names, URLs, statuses, and citations before report projection, while retaining older available reviews that have no condition field.
- [x] Render each condition and its WCAG correlation in `index.html` and `src/main.mjs`. Use DOM text nodes for model text, link only to canonical WCAG URLs and run-local evidence anchors, and display an explicit conformance limitation.
- [x] Add focused Python contract tests in `tests/test_report_correlations.py` for mapped and unmapped conditions, citation scope, and malformed data. Check JavaScript syntax and whitespace.
- [x] Add PDF source IDs, titles, locators, source types, and published links as a fallback for non-WCAG conditions. Validate that WCAG and PDF source IDs are mutually exclusive and that a citation cannot be altered in the handoff.

## Verification notes

The focused contract checks pass, JavaScript syntax is valid, and `git diff --check` is clean. Broad legacy suites were attempted; older tests expect demo links and sample report markup that were removed before this change. One representative Python failure expects `href="/demo/fixed"` on the landing page, which the current base page lacks. The Node suite contains similar sample report assertions. These unrelated failures remain outside this feature's scope.
