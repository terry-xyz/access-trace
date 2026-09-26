"""Focused checks for condition-specific WCAG correlations."""

import unittest

from access_trace.evidence import _reporting
from access_trace.report import ReviewError, validate_review


ACTION = {"id": "action:1", "kind": "action", "sequence": 1}
OBSERVATION = {"id": "observation:1", "kind": "observation", "sequence": 1}
ALLOWED = {"action:1": ACTION, "observation:1": OBSERVATION}


def review(criterion_id="2.4.7", references=None):
    return {
        "explanation": "A focus indicator was not visible.",
        "evidenceReferences": ["action:1", "observation:1"],
        "confidence": "medium",
        "proposedFix": "Make the focused control visually apparent.",
        "conditions": [{
            "condition": "The focused control has no visible indicator.",
            "wcagCriterionId": criterion_id,
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

    def test_unknown_criterion_and_condition_citation_are_rejected(self):
        with self.assertRaises(ReviewError):
            validate_review(review("9.9.9"), ALLOWED)
        with self.assertRaises(ReviewError):
            validate_review(review(["2.4.7"]), ALLOWED)
        with self.assertRaises(ReviewError):
            validate_review(review(references=["action:9"]), ALLOWED)

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


if __name__ == "__main__":
    unittest.main()
