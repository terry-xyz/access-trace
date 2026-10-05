import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from access_trace.browser import IsolatedKeyboardBrowser
from access_trace.domain import create_run
from access_trace.journey import LIFECYCLE_FIELDS, execute_assessment


class JourneyTests(unittest.TestCase):
    def test_goals_use_the_general_planner_flow_for_web_and_uploaded_pages(self):
        for target in (
            "https://example.test/",
            "http://127.0.0.1:8080/sites/" + "a" * 32 + "/index.html",
        ):
            for goal_status in ("completed", "not-possible", "not-accessibility-related"):
                with self.subTest(target=target, goal_status=goal_status), tempfile.TemporaryDirectory() as directory:
                    run = create_run({"targetUrl": target, "goal": "Submit the contact form"}, 8080)
                    browser = Mock(spec=IsolatedKeyboardBrowser)
                    browser.needs_headful_retry.return_value = False
                    browser.observe.return_value = {
                        "url": target,
                        "title": "Private page title",
                        "focus": {"role": "textbox", "tag": "input", "stableId": "name", "isStable": True},
                        "controls": [],
                        "lifecycle": {**dict.fromkeys(LIFECYCLE_FIELDS, False), "pageOpen": True},
                    }
                    planner = Mock()
                    planner.next_action.side_effect = [
                        {"kind": "type", "field": "name", "text": "Avery", "goalStatus": "in-progress", "goalReason": None},
                        {"kind": "complete", "goalStatus": goal_status, "goalReason": None if goal_status == "completed" else "Cannot assess this goal."},
                    ]
                    with patch("access_trace.journey.IsolatedKeyboardBrowser", return_value=browser) as factory:
                        result = execute_assessment(run, Path(directory), planner)
                    self.assertEqual("COMPLETED" if goal_status == "completed" else "INCONCLUSIVE", result["status"])
                    self.assertEqual(goal_status, result["observations"][-1]["goalProgress"]["status"])
                    self.assertEqual("[redacted]", result["observations"][-1]["title"])
                    self.assertEqual(5, result["actions"][0]["characterCount"])
                    self.assertNotIn("text", result["actions"][0])
                    self.assertEqual(target.startswith("http://127.0.0.1"), factory.call_args.kwargs.get("restrict_network", False))
                    browser.type_text.assert_called_once_with("Avery")
                    browser.close.assert_called_once()

    def test_whole_page_scan_records_keyboard_coverage_without_a_planner_turn(self):
        target = "https://example.test/"
        run = create_run({"targetUrl": target, "pageOnly": True}, 8080)
        browser = Mock(spec=IsolatedKeyboardBrowser)
        browser.needs_headful_retry.return_value = False
        control = {"role": "button", "stableId": "continue", "isStable": True}
        observation = {
            "url": target,
            "focus": control,
            "controls": [control],
            "controlCount": 1,
            "lifecycle": {**dict.fromkeys(LIFECYCLE_FIELDS, False), "pageOpen": True},
        }
        browser.observe.return_value = {**observation, "focus": {"stableId": "document"}}
        browser.observe_focus.return_value = observation

        def save_screenshot(destination):
            destination.write_bytes(b"\x89PNG\r\n\x1a\n")
            return destination.name

        browser.capture_redacted_screenshot.side_effect = save_screenshot
        planner = Mock()
        with tempfile.TemporaryDirectory() as directory, patch("access_trace.journey.IsolatedKeyboardBrowser", return_value=browser):
            result = execute_assessment(run, Path(directory), planner)
        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual(1, result["observations"][-1]["coverage"]["controlsObserved"])
        self.assertIsNotNone(result["stoppingScreenshotRef"])
        browser.press_key.assert_called_once_with("Tab")
        planner.next_action.assert_not_called()
        browser.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
