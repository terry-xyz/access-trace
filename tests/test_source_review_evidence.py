import unittest

from access_trace.source_review import _bounded_evidence


class SourceReviewEvidenceTests(unittest.TestCase):
    def test_completed_run_passes_report_finding_to_source_reviewer(self):
        run = {
            "status": "COMPLETED",
            "evidenceHandoff": {
                "assessment": {"goal": "Submit the form"},
                "observations": [],
                "actions": [],
                "terminal": {},
                "stopping": {},
                "reporting": {
                    "status": "available",
                    "explanation": "The label is missing from the email input.",
                    "proposedFix": "Connect the label to the input.",
                    "evidenceReferences": ["focus:2"],
                },
            },
        }

        evidence = _bounded_evidence(run)

        self.assertEqual("COMPLETED", evidence["terminalStatus"])
        self.assertEqual(
            "The label is missing from the email input.",
            evidence["reportFinding"]["explanation"],
        )
        self.assertEqual(["focus:2"], evidence["reportFinding"]["evidenceReferences"])


if __name__ == "__main__":
    unittest.main()
