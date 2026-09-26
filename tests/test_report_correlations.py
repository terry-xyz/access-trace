"""Focused checks for condition-specific WCAG and supplied-source citations."""

import unittest

from access_trace.evidence import _reporting
from access_trace.report import REVIEW_PROMPT_INSTRUCTIONS, ReviewError, validate_review


ACTION = {"id": "action:1", "kind": "action", "sequence": 1}
OBSERVATION = {"id": "observation:1", "kind": "observation", "sequence": 1}
ALLOWED = {"action:1": ACTION, "observation:1": OBSERVATION}


def review(criterion_id="2.4.7", source_id=None, references=None):
    return {
        "explanation": "A focus indicator was not visible.",
        "evidenceReferences": ["action:1", "observation:1"],
        "confidence": "medium",
        "proposedFix": "Make the focused control visually apparent.",
        "conditions": [{
            "condition": "The focused control has no visible indicator.",
            "wcagCriterionId": criterion_id,
            "sourceReferenceId": source_id,
            "evidenceReferences": references or ["observation:1"],
        }],
    }


class ReportCorrelationTests(unittest.TestCase):
    def test_canonical_mapping_and_condition_specific_evidence_survive_handoff(self):
        validated = validate_review(review(), ALLOWED)
        condition = validated["conditions"][0]
        self.assertEqual(condition["wcagCriterion"]["id"], "2.4.7")
        self.assertEqual(condition["wcagCriterion"]["name"], "Focus Visible")
        self.assertEqual(condition["evidenceReferences"], [OBSERVATION])

        projected = _reporting(
            {"status": "available", **validated},
            [{"kind": "action", "sequence": 1}, {"kind": "observation", "sequence": 1}],
        )
        self.assertEqual(projected["status"], "available")
        self.assertEqual(projected["conditions"], validated["conditions"])

    def test_insufficient_mapping_is_explicitly_unmapped(self):
        validated = validate_review(review(None), ALLOWED)
        condition = validated["conditions"][0]
        self.assertEqual(condition["mappingStatus"], "unmapped")
        self.assertIsNone(condition["wcagCriterion"])
        self.assertIsNone(condition["sourceReference"])

    def test_non_wcag_issue_cites_the_who_itu_requirement_and_its_pdf_page(self):
        validated = validate_review(review(None, "WHO-ITU-14"), ALLOWED)
        condition = validated["conditions"][0]
        self.assertEqual(condition["mappingStatus"], "source")
        self.assertIsNone(condition["wcagCriterion"])
        self.assertEqual(condition["sourceReference"]["locator"], "Requirement 14, p. 6")
        self.assertEqual(condition["sourceReference"]["sourceType"], "Toolkit requirement")
        self.assertTrue(condition["sourceReference"]["url"].endswith("#page=16"))
        projected = _reporting(
            {"status": "available", **validated},
            [{"kind": "action", "sequence": 1}, {"kind": "observation", "sequence": 1}],
        )
        self.assertEqual(projected["conditions"][0], condition)

    def test_runtime_review_prompt_contains_all_three_source_families(self):
        for source_id in ("WHO-ITU-14", "ETSI-5.9", "BRUNEL-FORMS"):
            self.assertIn(source_id, REVIEW_PROMPT_INSTRUCTIONS)

    def test_etsi_and_research_sources_keep_distinct_source_types(self):
        etsi = validate_review(review(None, "ETSI-5.9"), ALLOWED)
        brunel = validate_review(review(None, "BRUNEL-FORMS"), ALLOWED)
        self.assertEqual(etsi["conditions"][0]["sourceReference"]["sourceType"], "Standard requirement")
        self.assertEqual(brunel["conditions"][0]["sourceReference"]["sourceType"], "Research finding")

    def test_unknown_criterion_and_condition_citation_are_rejected(self):
        with self.assertRaises(ReviewError):
            validate_review(review("9.9.9"), ALLOWED)
        with self.assertRaises(ReviewError):
            validate_review(review(["2.4.7"]), ALLOWED)
        with self.assertRaises(ReviewError):
            validate_review(review(references=["action:9"]), ALLOWED)
        with self.assertRaises(ReviewError):
            validate_review(review(None, "UNKNOWN-SOURCE"), ALLOWED)
        with self.assertRaises(ReviewError):
            validate_review(review("2.4.7", "WHO-ITU-14"), ALLOWED)

    def test_tampered_mapping_does_not_enter_handoff(self):
        validated = validate_review(review(), ALLOWED)
        validated["conditions"][0]["wcagCriterion"]["name"] = "Wrong name"
        projected = _reporting(
            {"status": "available", **validated},
            [{"kind": "action", "sequence": 1}, {"kind": "observation", "sequence": 1}],
        )
        self.assertEqual(projected["status"], "pending")
        self.assertEqual(projected["conditions"], [])

    def test_malformed_mapping_status_does_not_break_handoff(self):
        validated = validate_review(review(), ALLOWED)
        validated["conditions"][0]["mappingStatus"] = []
        projected = _reporting(
            {"status": "available", **validated},
            [{"kind": "action", "sequence": 1}, {"kind": "observation", "sequence": 1}],
        )
        self.assertEqual(projected["status"], "pending")

    def test_tampered_source_reference_does_not_enter_handoff(self):
        validated = validate_review(review(None, "WHO-ITU-14"), ALLOWED)
        validated["conditions"][0]["sourceReference"]["locator"] = "Requirement 99"
        projected = _reporting(
            {"status": "available", **validated},
            [{"kind": "action", "sequence": 1}, {"kind": "observation", "sequence": 1}],
        )
        self.assertEqual(projected["status"], "pending")


if __name__ == "__main__":
    unittest.main()
