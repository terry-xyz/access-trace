"""Current run-input, evidence, and planner-boundary contracts."""

import unittest
from unittest.mock import patch

from access_trace.domain import (
    ValidationError,
    configured_site_page_limit,
    create_run,
)
from access_trace.evidence import build_evidence_handoff
from access_trace.planner import PlannerError, validate_action


CONTROLLED_PORT = 4173
FIXED_URL = "http://127.0.0.1:4173/docs/demos/fixed/index.html"


class AssessmentContractTests(unittest.TestCase):
    def test_run_creation_preserves_scope_and_builds_a_versioned_evidence_handoff(self):
        run = create_run(
            {"targetUrl": FIXED_URL, "goal": "Submit the contact form"},
            CONTROLLED_PORT,
        )

        self.assertEqual("goal-focused", run["assessmentScope"])
        self.assertEqual("Submit the contact form", run["goal"])
        self.assertEqual("fixed", run["targetVersion"])
        self.assertEqual("access-trace.evidence.v1", run["evidenceHandoff"]["schema"])
        self.assertEqual(run["id"], run["evidenceHandoff"]["runId"])
        self.assertEqual("IN_PROGRESS", run["evidenceHandoff"]["terminal"]["status"])

    def test_blank_goal_selects_whole_site_and_arbitrary_web_targets_remain_web_runs(self):
        run = create_run(
            {"targetUrl": "https://example.test/a", "goal": "  "},
            CONTROLLED_PORT,
        )

        self.assertEqual("whole-site", run["assessmentScope"])
        self.assertIsNone(run["goal"])
        self.assertEqual("web", run["targetVersion"])
        self.assertEqual("whole-site", run["evidenceHandoff"]["assessment"]["assessmentScope"])

    def test_run_creation_rejects_invalid_urls_credentials_and_mismatched_scope(self):
        invalid_payloads = [
            {"targetUrl": ""},
            {"targetUrl": "javascript:alert(1)"},
            {"targetUrl": "https://user:pass@example.test/"},
            {"targetUrl": FIXED_URL, "assessmentScope": "whole-site", "goal": "Submit the contact form"},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                create_run(payload, CONTROLLED_PORT)

    def test_run_page_limit_and_simulation_mode_are_strictly_validated(self):
        for value in (-1, 501, True, 1.5):
            with self.subTest(sitePageLimit=value), self.assertRaises(ValidationError):
                create_run({"targetUrl": FIXED_URL, "sitePageLimit": value}, CONTROLLED_PORT)
        with self.assertRaises(ValidationError):
            create_run({"targetUrl": FIXED_URL, "simulationMode": "true"}, CONTROLLED_PORT)

    def test_site_page_limit_configuration_is_bounded_and_zero_means_uncapped(self):
        with patch.dict("os.environ", {"ACCESS_TRACE_MAX_SITE_PAGES": "0"}):
            self.assertEqual(0, configured_site_page_limit())
        with patch.dict("os.environ", {"ACCESS_TRACE_MAX_SITE_PAGES": "900"}):
            self.assertEqual(500, configured_site_page_limit())
        with patch.dict("os.environ", {"ACCESS_TRACE_MAX_SITE_PAGES": "invalid"}):
            self.assertEqual(25, configured_site_page_limit())

    def test_evidence_handoff_refresh_keeps_run_scope_and_privacy_bounds(self):
        run = create_run({"targetUrl": FIXED_URL}, CONTROLLED_PORT)
        handoff = build_evidence_handoff(run)

        self.assertEqual(run["id"], handoff["runId"])
        self.assertEqual("whole-site", handoff["assessment"]["assessmentScope"])
        self.assertEqual([{"kind": "observation", "sequence": 1}], handoff["evidenceReferences"])
        self.assertFalse(handoff["privacy"]["rawValuesRetained"])
        self.assertFalse(handoff["privacy"]["pasteDataRetained"])
        self.assertFalse(handoff["privacy"]["pageSourceRetained"])

    def test_planner_normalizes_permitted_keys_and_rejects_unfocused_typing(self):
        key = validate_action({"kind": "key", "key": "Tab"}, {"goal": None})
        self.assertEqual({"kind": "key", "key": "Tab", "tabSteps": 1}, key)

        focused = {
            "goal": "Fill the name field",
            "pageEvidence": {
                "focus": {
                    "stableId": "name",
                    "role": "textbox",
                    "tag": "input",
                    "isStable": True,
                }
            },
        }
        self.assertEqual(
            {"kind": "type", "field": "name", "text": "Avery"},
            validate_action({"kind": "type", "field": "name", "text": "Avery"}, focused),
        )
        with self.assertRaises(PlannerError):
            validate_action({"kind": "type", "field": "email", "text": "a@example.test"}, focused)
        with self.assertRaises(PlannerError):
            validate_action({"kind": "key", "key": "Escape; rm -rf"}, {"goal": None})


if __name__ == "__main__":
    unittest.main()
