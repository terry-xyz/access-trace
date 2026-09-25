import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from access_trace.server import create_server


class AssessmentTargetTests(unittest.TestCase):
    def setUp(self):
        self.run_directory = Path(tempfile.mkdtemp())
        self.server = create_server("127.0.0.1", 0, self.run_directory)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{0}".format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def request(self, method, path, payload=None):
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_demo_versions_expose_the_same_form_and_distinct_submit_behaviour(self):
        fixed_status, fixed_page = self.raw_request("/demo/fixed")
        broken_status, broken_page = self.raw_request("/demo/broken")

        self.assertEqual(200, fixed_status)
        self.assertEqual(200, broken_status)
        for page in (fixed_page, broken_page):
            self.assertIn('for="name"', page)
            self.assertIn('for="email"', page)
            self.assertIn('for="message"', page)
            self.assertIn('id="submit"', page)
            self.assertIn("Message sent", page)
            self.assertIn('role="status"', page)

        self.assertIn('data-version="fixed"', fixed_page)
        self.assertIn('data-version="broken"', broken_page)
        self.assertIn('form.addEventListener("submit"', fixed_page)
        self.assertIn('event.preventDefault()', broken_page)

    def test_landing_page_exposes_the_fresh_run_inputs(self):
        status, page = self.raw_request("/")

        self.assertEqual(200, status)
        self.assertIn('id="target-url"', page)
        self.assertIn('id="goal"', page)
        self.assertIn('id="simulation-mode"', page)
        self.assertIn("Start fresh run", page)

    def test_starting_a_goal_run_persists_context_and_a_bounded_first_observation(self):
        status, run = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
        )

        self.assertEqual(201, status)
        self.assertEqual("goal-focused", run["assessmentScope"])
        self.assertEqual("Submit the contact form", run["goal"])
        self.assertTrue(run["simulationMode"])
        self.assertEqual("keyboard-only", run["interactionProfile"])
        self.assertEqual("IN_PROGRESS", run["status"])
        self.assertEqual("fixed", run["targetVersion"])
        self.assertEqual(1, len(run["observations"]))

        observation = run["observations"][0]
        self.assertEqual(self.base_url + "/demo/fixed", observation["url"])
        self.assertIn("Contact form", observation["title"])
        self.assertEqual("body", observation["focus"]["tag"])
        self.assertEqual("Submit", observation["controls"][-1]["accessibleName"])
        self.assertFalse(observation["success"]["matched"])
        self.assertEqual("Message sent", observation["success"]["condition"])
        self.assertEqual([], run["actions"])

        serialized = json.dumps(run)
        self.assertNotIn("Avery", serialized)
        self.assertNotIn("avery@example.test", serialized)
        self.assertNotIn("A fictional message", serialized)
        self.assertNotIn("<form", serialized)

        stored = self.run_directory / (run["id"] + ".json")
        self.assertTrue(stored.exists())
        self.assertEqual(run, json.loads(stored.read_text()))

    def test_starting_without_a_goal_uses_whole_site_scope_and_preserves_simulation_mode(self):
        status, run = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/broken",
                "simulationMode": False,
            },
        )

        self.assertEqual(201, status)
        self.assertEqual("whole-site", run["assessmentScope"])
        self.assertIsNone(run["goal"])
        self.assertFalse(run["simulationMode"])
        self.assertIsNone(run["successCondition"])
        self.assertEqual("not-started", run["observations"][0]["coverage"]["status"])
        self.assertNotIn("Message sent", json.dumps(run["observations"][0]["coverage"]))

    def test_an_unknown_goal_is_carried_without_being_reinterpreted(self):
        status, run = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Export the private customer list",
            },
        )

        self.assertEqual(201, status)
        self.assertEqual("goal-focused", run["assessmentScope"])
        self.assertEqual("Export the private customer list", run["goal"])
        self.assertIsNone(run["successCondition"])
        self.assertEqual(
            "Export the private customer list",
            run["observations"][0]["goalProgress"]["goal"],
        )

    def test_fetching_a_run_returns_the_same_bounded_record(self):
        _, created = self.request(
            "POST",
            "/api/runs",
            {"targetUrl": self.base_url + "/demo/fixed"},
        )

        status, fetched = self.request("GET", "/api/runs/" + created["id"])

        self.assertEqual(200, status)
        self.assertEqual(created, fetched)

    def test_non_local_or_unrecognized_targets_are_rejected(self):
        for target_url in (
            "https://example.com/demo/fixed",
            self.base_url + "/demo/other",
        ):
            with self.assertRaises(HTTPError) as error:
                self.request("POST", "/api/runs", {"targetUrl": target_url})
            self.assertEqual(400, error.exception.code)

    def raw_request(self, path):
        with urlopen(self.base_url + path, timeout=2) as response:
            return response.status, response.read().decode("utf-8")


if __name__ == "__main__":
    unittest.main()
