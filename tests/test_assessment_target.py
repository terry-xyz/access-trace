import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest import mock

from access_trace.browser import BrowserCleanupError, BrowserError, IsolatedKeyboardBrowser
from access_trace.domain import create_run
from access_trace.journey import (
    CodexPlanner,
    PlannerError,
    _complete_if_verified,
    execute_fixed_goal,
    redacted_observation,
)
from access_trace.server import create_server


class DeterministicTestPlanner:
    values = {
        "name": "Avery Example",
        "email": "avery@example.test",
        "message": "A fictional message",
    }

    def next_action(self, context):
        page = context["pageEvidence"]
        focus = page["focus"]
        if page["successMatched"]:
            return {"kind": "complete"}
        if focus["role"] == "document":
            return {"kind": "key", "key": "Tab"}
        if focus["stableId"] in self.values and not focus["acceptedInput"]:
            return {
                "kind": "type",
                "field": focus["stableId"],
                "text": self.values[focus["stableId"]],
            }
        if focus["role"] == "button" and focus["accessibleName"] == "Submit":
            return {"kind": "key", "key": "Enter"}
        return {"kind": "key", "key": "Tab"}


class FakePlannerTransport:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def __call__(self, endpoint, headers, body, timeout):
        self.calls.append(
            {
                "endpoint": endpoint,
                "headers": headers,
                "body": body,
                "timeout": timeout,
            }
        )
        return json.dumps({"output_text": self.output}).encode("utf-8")


class AssessmentTargetTests(unittest.TestCase):
    def setUp(self):
        self.run_directory = Path(tempfile.mkdtemp())
        self.server = create_server(
            "127.0.0.1",
            0,
            self.run_directory,
            planner_factory=DeterministicTestPlanner,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{0}".format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def request(self, method, path, payload=None, timeout=2):
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
        with urlopen(request, timeout=timeout) as response:
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
        _, fixed_page = self.raw_request("/demo/fixed")
        served_title = fixed_page.split("<title>", 1)[1].split("</title>", 1)[0]
        self.assertEqual(served_title, observation["title"])
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

    def test_fixed_contact_goal_completes_with_redacted_keyboard_evidence(self):
        _, created = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
        )

        status, completed = self.request(
            "POST", "/api/runs/{0}/execute".format(created["id"]), timeout=10
        )

        self.assertEqual(200, status)
        self.assertEqual("COMPLETED", completed["status"])
        self.assertTrue(completed["simulationMode"])
        self.assertEqual("verified", completed["browserSession"]["cleanup"]["status"])
        self.assertTrue(completed["browserSession"]["cleanup"]["profileRemoved"])
        self.assertIsNone(completed["browserFailure"])
        self.assertGreater(completed["durationMs"], 0)
        self.assertEqual(completed["interactionCount"], len(completed["actions"]))
        self.assertGreaterEqual(len(completed["observations"]), 7)
        self.assertEqual("Message sent", completed["stoppingPoint"]["successCondition"])
        self.assertTrue(completed["stoppingPoint"]["successMatched"])
        screenshot = self.run_directory / completed["stoppingScreenshotRef"]
        self.assertTrue(screenshot.is_file())
        self.assertTrue(screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

        action_kinds = [action["kind"] for action in completed["actions"]]
        self.assertEqual(["key", "type", "key", "type", "key", "type", "key", "key"], action_kinds)
        self.assertEqual("Enter", completed["actions"][-1]["key"])
        self.assertTrue(completed["observations"][-1]["success"]["matched"])
        self.assertEqual("button", completed["observations"][-1]["focus"]["tag"])
        self.assertEqual("Submit", completed["observations"][-1]["focus"]["accessibleName"])
        self.assertTrue(all("text" not in action for action in completed["actions"]))
        self.assertIn("characterCount", json.dumps(completed))
        self.assertNotIn("Avery Example", json.dumps(completed))
        self.assertNotIn("avery@example.test", json.dumps(completed))
        self.assertNotIn("A fictional message", json.dumps(completed))
        self.assertNotIn("clipboard", json.dumps(completed).lower())

        stored = self.run_directory / (created["id"] + ".json")
        self.assertEqual(completed, json.loads(stored.read_text()))

    def test_fixed_goal_without_evidence_directory_cannot_complete(self):
        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )

        completed = execute_fixed_goal(run, planner=DeterministicTestPlanner())

        self.assertEqual("INCONCLUSIVE", completed["status"])
        self.assertIsNone(completed["stoppingScreenshotRef"])
        self.assertEqual("missing-evidence-directory", completed["warnings"][0]["kind"])

    def test_page_derived_strings_are_bounded_before_evidence(self):
        oversized = "x" * 10000
        observation = redacted_observation(
            {
                "url": self.base_url + "/demo/fixed/" + oversized,
                "title": oversized,
                "focus": {
                    "role": oversized,
                    "accessibleName": oversized,
                    "tag": oversized,
                    "stableId": oversized,
                    "isStable": True,
                    "characterCount": oversized,
                    "acceptedInput": oversized,
                    "validationState": oversized,
                },
                "controls": [
                    {
                        "role": oversized,
                        "accessibleName": oversized,
                        "tag": oversized,
                        "stableId": oversized,
                        "focusable": True,
                        "isStable": True,
                        "characterCount": oversized,
                        "acceptedInput": oversized,
                        "validationState": oversized,
                    }
                ],
                "successMatched": False,
                "lifecycle": {},
            },
            self.base_url + "/demo/fixed",
        )

        serialized = json.dumps(observation)
        self.assertLessEqual(len(observation["url"]), 256)
        self.assertLessEqual(len(observation["title"]), 80)
        self.assertNotIn(oversized, serialized)
        self.assertLessEqual(len(observation["focus"]["stableId"]), 80)
        self.assertLessEqual(len(observation["controls"][0]["accessibleName"]), 80)
        self.assertIsInstance(observation["controls"][0]["characterCount"], int)
        self.assertIsInstance(observation["controls"][0]["acceptedInput"], bool)

        reflected = redacted_observation(
            {
                "url": (
                    self.base_url
                    + "/demo/fixed?name=Avery%20Example&email=avery%40example.test#message=A%20fictional%20message"
                ),
                "title": "Sent Avery%20Example avery%40example.test",
                "focus": {},
                "controls": [],
                "successMatched": False,
                "lifecycle": {},
            },
            self.base_url + "/demo/fixed",
            sensitive_values=(
                "Avery Example",
                "avery@example.test",
                "A fictional message",
            ),
        )

        reflected_serialized = json.dumps(reflected)
        self.assertEqual(self.base_url + "/demo/fixed", reflected["url"])
        self.assertEqual("[redacted]", reflected["title"])
        self.assertNotIn("Avery Example", reflected_serialized)
        self.assertNotIn("avery@example.test", reflected_serialized)
        self.assertNotIn("Avery%20Example", reflected_serialized)
        self.assertNotIn("avery%40example.test", reflected_serialized)
        self.assertFalse(reflected["lifecycle"]["offLoopbackRedirect"])
        self.assertEqual([], reflected["warnings"])

        path_reflected = redacted_observation(
            {
                "url": self.base_url + "/demo/fixed/Avery%20Example",
                "title": "AccessTrace Contact form",
                "focus": {},
                "controls": [],
                "successMatched": False,
                "lifecycle": {},
            },
            self.base_url + "/demo/fixed",
            sensitive_values=("Avery Example",),
        )
        self.assertEqual(self.base_url + "/[redacted-path]", path_reflected["url"])
        self.assertTrue(path_reflected["lifecycle"]["navigationRedirect"])
        self.assertEqual([{"kind": "navigation-redirect"}], path_reflected["warnings"])

        for settled_path in ("/demo/broken", "/other/path"):
            redirected = redacted_observation(
                {
                    "url": self.base_url + settled_path + "?token=secret#fragment",
                    "title": "AccessTrace Contact form",
                    "focus": {},
                    "controls": [],
                    "successMatched": False,
                    "lifecycle": {},
                },
                self.base_url + "/demo/fixed",
            )
            self.assertEqual(self.base_url + settled_path, redirected["url"])
            self.assertTrue(redirected["lifecycle"]["navigationRedirect"])
            self.assertEqual(
                [{"kind": "navigation-redirect"}], redirected["warnings"]
            )

    def test_codex_planner_rejects_a_forged_editable_focus(self):
        context = {
            "pageEvidence": {
                "focus": {
                    "role": "button",
                    "tag": "button",
                    "stableId": "name",
                    "isStable": True,
                    "acceptedInput": False,
                }
            }
        }
        planner = CodexPlanner(
            endpoint="https://planner.example/v1/responses",
            model="planner-test-model",
            api_key="planner-test-secret",
            transport=FakePlannerTransport(
                '{"kind":"type","field":"name","text":"fictional"}'
            ),
        )

        with self.assertRaises(PlannerError):
            planner.next_action(context)

    def test_completed_requires_a_persisted_png_screenshot(self):
        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        run["actions"].append(
            {
                "kind": "key",
                "key": "Enter",
                "focusBefore": {"role": "button", "accessibleName": "Submit"},
            }
        )
        observation = run["observations"][0]
        observation["success"] = {"condition": "Message sent", "matched": True}
        browser = mock.Mock()
        browser.capture_redacted_screenshot.return_value = (
            run["id"] + "-stopping.png"
        )

        with self.assertRaises(BrowserError):
            _complete_if_verified(run, observation, 0.0, browser, self.run_directory)

        self.assertNotEqual("COMPLETED", run["status"])
        self.assertIsNone(run["stoppingScreenshotRef"])

    def test_default_server_uses_codex_planner_boundary(self):
        server = create_server("127.0.0.1", 0, Path(tempfile.mkdtemp()))
        try:
            self.assertIsInstance(server.planner_factory(), CodexPlanner)
        finally:
            server.server_close()

    def test_codex_planner_fails_truthfully_without_direct_model_configuration(self):
        with mock.patch.dict(
            os.environ,
            {
                "CODEX_PLANNER_ENDPOINT": "",
                "CODEX_PLANNER_MODEL": "",
                "CODEX_PLANNER_API_KEY": "",
            },
        ):
            with self.assertRaises(PlannerError):
                CodexPlanner().next_action({"pageEvidence": {"focus": {}}})

    def test_same_origin_path_redirect_makes_execution_inconclusive(self):
        class RedirectingBrowser:
            def __init__(self, target_url):
                self.url = target_url.replace("/demo/fixed", "/demo/broken")

            def observe(self):
                return {
                    "url": self.url,
                    "title": "AccessTrace Contact form",
                    "focus": {
                        "role": "document",
                        "accessibleName": "Fictional contact form",
                        "tag": "body",
                        "stableId": "document",
                        "isStable": True,
                    },
                    "controls": [],
                    "successMatched": False,
                    "lifecycle": {},
                }

            def close(self):
                return None

        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", RedirectingBrowser
        ):
            result = execute_fixed_goal(
                run,
                self.run_directory,
                planner=DeterministicTestPlanner(),
            )

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertTrue(result["observations"][0]["lifecycle"]["navigationRedirect"])
        self.assertIn(
            {"kind": "navigation-redirect"}, result["observations"][0]["warnings"]
        )

    def test_codex_planner_validates_the_action_boundary(self):
        context = {
            "goal": "Submit the contact form",
            "successCondition": "Message sent",
            "simulationMode": True,
            "interactionProfile": "keyboard-only",
            "pageEvidence": {
                "focus": {
                    "role": "document",
                    "accessibleName": "Fictional contact form",
                    "tag": "body",
                    "stableId": "document",
                    "isStable": True,
                    "characterCount": 0,
                    "acceptedInput": False,
                    "validationState": "not-observed",
                },
                "successMatched": False,
                "url": self.base_url + "/demo/fixed",
                "title": "AccessTrace Contact form",
                "controls": [],
                "untrusted": True,
            },
            "goalProgress": {},
            "warnings": [],
            "recentHistory": [],
        }

        transport = FakePlannerTransport('{"kind":"key","key":"Tab"}')
        planner = CodexPlanner(
            endpoint="https://planner.example/v1/responses",
            model="planner-test-model",
            api_key="planner-test-secret",
            transport=transport,
        )
        self.assertEqual({"kind": "key", "key": "Tab"}, planner.next_action(context))

        request = transport.calls[0]
        body = json.loads(request["body"])
        self.assertEqual("https://planner.example/v1/responses", request["endpoint"])
        self.assertEqual("Bearer planner-test-secret", request["headers"]["Authorization"])
        self.assertNotIn("tools", body)
        self.assertEqual("planner-test-model", body["model"])
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertNotIn("planner-test-secret", json.dumps(body))
        self.assertLessEqual(len(body["input"]), 12_000)

        echoed_credential = CodexPlanner(
            endpoint="https://planner.example/v1/responses",
            model="planner-test-model",
            api_key="planner-test-secret",
            transport=FakePlannerTransport(
                '{"kind":"key","key":"Tab"} planner-test-secret'
            ),
        )
        with self.assertRaises(PlannerError):
            echoed_credential.next_action(context)

        type_context = json.loads(json.dumps(context))
        type_context["pageEvidence"]["focus"].update(
            {
                "role": "textbox",
                "accessibleName": "Name",
                "tag": "input",
                "stableId": "name",
                "acceptedInput": False,
            }
        )
        type_planner = CodexPlanner(
            endpoint="https://planner.example/v1/responses",
            model="planner-test-model",
            api_key="planner-test-secret",
            transport=FakePlannerTransport(
                '{"kind":"type","field":"name","text":"fictional"}'
            ),
        )
        self.assertEqual(
            {"kind": "type", "field": "name", "text": "fictional"},
            type_planner.next_action(type_context),
        )

        invalid = CodexPlanner(
            endpoint="https://planner.example/v1/responses",
            model="planner-test-model",
            api_key="planner-test-secret",
            transport=FakePlannerTransport(
                '{"kind":"click","selector":"#submit"}'
            ),
        )
        with self.assertRaises(PlannerError):
            invalid.next_action(context)

        extra_field = CodexPlanner(
            endpoint="https://planner.example/v1/responses",
            model="planner-test-model",
            api_key="planner-test-secret",
            transport=FakePlannerTransport(
                '{"kind":"key","key":"Tab","extra":"ignored"}'
            ),
        )
        with self.assertRaises(PlannerError):
            extra_field.next_action(context)

    def test_browser_cleanup_removes_profile_and_reports_failure(self):
        profile = Path(tempfile.mkdtemp())
        (profile / "profile-marker").write_text("temporary")
        browser = object.__new__(IsolatedKeyboardBrowser)
        browser.profile_directory = profile
        browser.process = None
        browser.connection = None

        browser.close()

        self.assertFalse(profile.exists())

        failed_profile = Path(tempfile.mkdtemp())
        failed_browser = object.__new__(IsolatedKeyboardBrowser)
        failed_browser.profile_directory = failed_profile
        failed_browser.process = None
        failed_browser.connection = None
        with mock.patch(
            "access_trace.browser.shutil.rmtree",
            side_effect=OSError("profile is locked"),
        ):
            with self.assertRaises(BrowserCleanupError):
                failed_browser.close()
        self.assertTrue(failed_profile.exists())

    def test_cleanup_failure_downgrades_a_would_be_success(self):
        class CleanupFailingBrowser:
            def __init__(self, target_url):
                self.target_url = target_url
                self.focus_index = 0
                self.values = {}
                self.success = False
                self.focus_order = ["document", "name", "email", "message", "submit"]

            def observe(self):
                stable_id = self.focus_order[self.focus_index]
                if stable_id == "document":
                    focus = {
                        "role": "document",
                        "accessibleName": "Fictional contact form",
                        "tag": "body",
                        "stableId": "document",
                        "isStable": True,
                    }
                elif stable_id == "submit":
                    focus = {
                        "role": "button",
                        "accessibleName": "Submit",
                        "tag": "button",
                        "stableId": "submit",
                        "isStable": True,
                    }
                else:
                    focus = {
                        "role": "textbox",
                        "accessibleName": stable_id.title(),
                        "tag": "textarea" if stable_id == "message" else "input",
                        "stableId": stable_id,
                        "isStable": True,
                        "characterCount": len(self.values.get(stable_id, "")),
                        "acceptedInput": bool(self.values.get(stable_id)),
                        "validationState": "valid" if self.values.get(stable_id) else "not-observed",
                    }
                controls = [
                    {
                        "role": "textbox",
                        "accessibleName": field.title(),
                        "tag": "textarea" if field == "message" else "input",
                        "stableId": field,
                        "isStable": True,
                        "characterCount": len(self.values.get(field, "")),
                        "acceptedInput": bool(self.values.get(field)),
                        "validationState": "valid" if self.values.get(field) else "not-observed",
                    }
                    for field in ("name", "email", "message")
                ]
                controls.append(
                    {
                        "role": "button",
                        "accessibleName": "Submit",
                        "tag": "button",
                        "stableId": "submit",
                        "isStable": True,
                    }
                )
                return {
                    "url": self.target_url,
                    "title": "AccessTrace Contact form",
                    "focus": focus,
                    "controls": controls,
                    "successMatched": self.success,
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "popupObserved": False,
                        "crashed": False,
                    },
                }

            def press_key(self, key):
                if key == "Tab":
                    self.focus_index = min(self.focus_index + 1, len(self.focus_order) - 1)
                elif key == "Enter" and self.focus_order[self.focus_index] == "submit":
                    self.success = True

            def type_text(self, text):
                self.values[self.focus_order[self.focus_index]] = text

            def capture_redacted_screenshot(self, destination):
                destination.write_bytes(b"\x89PNG\r\n\x1a\n")
                return destination.name

            def close(self):
                raise BrowserCleanupError("profile is locked")

        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch("access_trace.journey.IsolatedKeyboardBrowser", CleanupFailingBrowser):
            completed = execute_fixed_goal(
                run,
                self.run_directory,
                planner=DeterministicTestPlanner(),
            )

        self.assertEqual("INCONCLUSIVE", completed["status"])
        self.assertEqual({"kind": "cleanup-failure"}, completed["browserFailure"])
        self.assertEqual("failed", completed["browserSession"]["cleanup"]["status"])
        self.assertFalse(completed["browserSession"]["cleanup"]["profileRemoved"])
        self.assertIn(
            {"kind": "browser-cleanup-failure"}, completed["warnings"]
        )

    def test_non_local_or_unrecognized_targets_are_rejected(self):
        for target_url in (
            "https://example.com/demo/fixed",
            "https://127.0.0.1:1/demo/fixed",
            "http://127.0.0.1:1/demo/fixed",
            self.base_url + "/demo/other",
        ):
            with self.assertRaises(HTTPError) as error:
                self.request("POST", "/api/runs", {"targetUrl": target_url})
            self.assertEqual(400, error.exception.code)

    def test_supported_loopback_aliases_use_the_controlled_server_port(self):
        for host in ("localhost", "127.0.0.1", "[::1]"):
            status, run = self.request(
                "POST",
                "/api/runs",
                {"targetUrl": "http://{0}:{1}/demo/fixed".format(host, self.server.server_port)},
            )
            self.assertEqual(201, status)
            self.assertEqual("fixed", run["targetVersion"])

    def test_an_arbitrary_host_header_does_not_define_the_controlled_origin(self):
        body = json.dumps({"targetUrl": self.base_url + "/demo/fixed"}).encode("utf-8")
        request = Request(
            self.base_url + "/api/runs",
            data=body,
            headers={"Content-Type": "application/json", "Host": "attacker.example"},
            method="POST",
        )

        with urlopen(request, timeout=2) as response:
            run = json.loads(response.read().decode("utf-8"))

        self.assertEqual(201, response.status)
        self.assertEqual(self.base_url + "/demo/fixed", run["targetUrl"])

        landing_request = Request(
            self.base_url + "/",
            headers={"Host": "attacker.example"},
            method="GET",
        )
        with urlopen(landing_request, timeout=2) as landing_response:
            landing_page = landing_response.read().decode("utf-8")

        self.assertIn(self.base_url + "/demo/fixed", landing_page)
        self.assertNotIn("attacker.example", landing_page)

    def raw_request(self, path):
        with urlopen(self.base_url + path, timeout=2) as response:
            return response.status, response.read().decode("utf-8")


if __name__ == "__main__":
    unittest.main()
