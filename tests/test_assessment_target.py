import base64
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest import mock

from access_trace.browser import (
    BrowserActionError,
    BrowserCleanupError,
    BrowserError,
    IsolatedKeyboardBrowser,
    MAX_PLANNER_SCREENSHOT_BYTES,
    _UploadedPageRequestPolicy,
)
from access_trace.domain import configured_site_page_limit, create_run
from access_trace.journey import (
    CodexPlanner,
    PlannerError,
    _complete_if_verified,
    execute_assessment,
    execute_contact_goal,
    execute_fixed_goal,
    redacted_observation,
)
from access_trace.planner import (
    CODEX_DISABLED_FEATURES,
    CODEX_OUTPUT_SCHEMA,
    _codex_executable,
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


class FakeCodexProcess:
    """Popen substitute that never starts a process on the host."""

    def __init__(self, output, returncode=None, stderr=b"", timeout=False, on_communicate=None):
        self.output = output
        self.returncode = returncode
        self.stderr = stderr
        self.timeout = timeout
        self.on_communicate = on_communicate
        self.terminated = False
        self.killed = False
        self.communicate_calls = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        if self.timeout and not self.terminated:
            raise subprocess.TimeoutExpired(["codex", "exec"], timeout)
        if self.on_communicate is not None:
            self.on_communicate()
        if self.returncode is None:
            self.returncode = 0
        return self.output, self.stderr

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


def codex_output(action):
    message = json.dumps(action, separators=(",", ":"))
    event = {"type": "item.completed", "item": {"type": "agent_message", "text": message}}
    return (json.dumps(event) + "\n").encode("utf-8")


class DeterministicContactBrowser:
    """Test seam for journey evidence without depending on CDP timing."""

    def __init__(self, target_url):
        self.target_url = target_url
        self.focus = "document"
        self.field_lengths = {"name": 0, "email": 0, "message": 0}
        self.success = False

    @property
    def broken(self):
        return self.target_url.endswith("/demo/broken")

    def _focus(self):
        if self.focus == "document":
            return {
                "role": "document",
                "accessibleName": "Fictional contact form",
                "tag": "body",
                "stableId": "document",
                "isStable": True,
            }
        if self.focus == "submit":
            return {
                "role": "button",
                "accessibleName": "Submit",
                "tag": "button",
                "stableId": "submit",
                "isStable": True,
            }
        length = self.field_lengths[self.focus]
        return {
            "role": "textbox",
            "accessibleName": self.focus.title(),
            "tag": "textarea" if self.focus == "message" else "input",
            "stableId": self.focus,
            "isStable": True,
            "characterCount": length,
            "acceptedInput": length > 0,
            "validationState": "valid" if length > 0 else "invalid",
        }

    def observe(self):
        controls = [
            {
                "role": "textbox",
                "accessibleName": field.title(),
                "tag": "textarea" if field == "message" else "input",
                "stableId": field,
                "focusable": True,
                "isStable": True,
                "characterCount": self.field_lengths[field],
                "acceptedInput": self.field_lengths[field] > 0,
                "validationState": (
                    "valid" if self.field_lengths[field] > 0 else "invalid"
                ),
            }
            for field in ("name", "email", "message")
        ]
        controls.append(
            {
                "role": "button",
                "accessibleName": "Submit",
                "tag": "button",
                "stableId": "submit",
                "focusable": True,
                "isStable": True,
            }
        )
        return {
            "url": self.target_url,
            "title": "AccessTrace Contact form",
            "focus": self._focus(),
            "controls": controls,
            "successMatched": self.success,
            "lifecycle": {
                "pageOpen": True,
                "dialogOpen": False,
                "dialogObserved": False,
                "popupObserved": False,
                "crashed": False,
                "offLoopbackRedirect": False,
                "navigationRedirect": False,
            },
        }

    def press_key(self, key):
        if key == "Tab":
            self.focus = {
                "document": "name",
                "name": "email",
                "email": "message",
                "message": "submit",
            }.get(self.focus, "submit")
        elif key == "Shift+Tab":
            self.focus = {
                "submit": "message",
                "message": "email",
                "email": "name",
                "name": "document",
            }.get(self.focus, "document")
        elif key in {"Enter", "Space"} and self.focus == "submit":
            self.success = not self.broken

    def type_text(self, text):
        self.field_lengths[self.focus] = len(text)

    def capture_redacted_screenshot(self, destination):
        destination.write_bytes(b"\x89PNG\r\n\x1a\n")
        return destination.name

    def close(self):
        return None


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
        self.assertIn('id="assessment-goal"', page)
        self.assertIn('id="simulation-mode"', page)
        self.assertIn('id="local-html-file"', page)
        self.assertIn("Start assessment", page)
        self.assertIn('href="/demo/fixed"', page)
        self.assertIn('href="/demo/broken"', page)

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
        config_status, config = self.request("GET", "/api/config")
        status, run = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/broken",
                "simulationMode": False,
            },
        )

        self.assertEqual(201, status)
        self.assertEqual(200, config_status)
        self.assertEqual(config["defaultSitePageLimit"], run["sitePageLimit"])
        self.assertEqual("whole-site", run["assessmentScope"])
        self.assertIsNone(run["goal"])
        self.assertFalse(run["simulationMode"])
        self.assertIsNone(run["successCondition"])
        self.assertEqual("not-started", run["observations"][0]["coverage"]["status"])
        self.assertNotIn("Message sent", json.dumps(run["observations"][0]["coverage"]))

    def test_site_page_limit_is_editable_and_zero_is_stored_as_no_limit(self):
        status, run = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "sitePageLimit": 3,
            },
        )
        self.assertEqual(201, status)
        self.assertEqual(3, run["sitePageLimit"])

        status, run = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "sitePageLimit": 0,
            },
        )
        self.assertEqual(201, status)
        self.assertEqual(0, run["sitePageLimit"])

        with self.assertRaises(HTTPError) as error:
            self.request(
                "POST",
                "/api/runs",
                {
                    "targetUrl": self.base_url + "/demo/fixed",
                    "sitePageLimit": 501,
                },
            )
        response = json.loads(error.exception.read().decode("utf-8"))
        self.assertEqual(400, error.exception.code)
        self.assertIn("0 to 500", response["error"]["message"])

    def test_whole_site_execution_completes_only_after_declared_focus_coverage(self):
        planner_contexts = []

        class WholeSitePlanner:
            def next_action(self, context):
                planner_contexts.append(context)
                if context["coverage"]["status"] == "completed":
                    return {"kind": "complete"}
                return {"kind": "key", "key": "Tab"}

        self.server.planner_factory = WholeSitePlanner
        _, created = self.request(
            "POST",
            "/api/runs",
            {"targetUrl": self.base_url + "/demo/fixed"},
        )

        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", DeterministicContactBrowser
        ):
            status, completed = self.request(
                "POST", "/api/runs/{0}/execute".format(created["id"]), timeout=30
            )

        self.assertEqual(200, status)
        self.assertEqual("COMPLETED", completed["status"])
        self.assertIsNone(completed["successCondition"])
        self.assertIsNone(completed["stoppingPoint"]["successCondition"])
        self.assertIsNone(completed["stoppingPoint"]["successMatched"])
        self.assertEqual("completed", completed["observations"][-1]["coverage"]["status"])
        self.assertTrue(completed["observations"][-1]["coverage"]["completed"])
        self.assertFalse(completed["observations"][-1]["coverage"]["controlsTruncated"])
        self.assertTrue(any("coverage" in context for context in planner_contexts))
        self.assertTrue(all(context["assessmentScope"] == "whole-site" for context in planner_contexts))
        self.assertTrue(all(context["goal"] is None for context in planner_contexts))
        self.assertNotIn("Message sent", json.dumps(completed["observations"][-1]["coverage"]))
        self.assertEqual("COMPLETED", completed["evidenceHandoff"]["terminal"]["status"])
        self.assertEqual(
            completed["observations"][-1]["coverage"],
            completed["evidenceHandoff"]["progress"]["coverage"],
        )
        self.assertIsNone(completed["evidenceHandoff"]["progress"]["goal"])

    def test_whole_site_visits_same_origin_pages_and_zero_config_means_all(self):
        target = self.base_url + "/docs/demos/fixed/index.html"
        page_two = self.base_url + "/docs/demos/fixed/one.html"
        page_three = self.base_url + "/docs/demos/fixed/two.html"
        run = create_run({"targetUrl": target}, self.server.server_port)
        visited = []
        discovered = []

        class SiteBrowser:
            def __init__(self, target_url):
                self.url = target_url

            def needs_headful_retry(self):
                return False

            def observe(self):
                return {
                    "url": self.url,
                    "title": "Site page",
                    "focus": {"role": "document", "stableId": "document", "isStable": True},
                    "controls": [],
                    "controlCount": 0,
                    "pageContentVisible": True,
                    "lifecycle": {
                        "pageOpen": True, "dialogOpen": False, "dialogObserved": False,
                        "popupObserved": False, "popupAttempted": False, "crashed": False,
                        "offLoopbackRedirect": False, "navigationRedirect": False,
                        "browserLoadError": False, "pageContentVisible": True,
                        "headfulFallback": False,
                    },
                }

            def discover_site_links(self):
                discovered.append(self.url)
                return [page_two, page_three]

            def navigate_to(self, url):
                visited.append(url)
                self.url = url

            def capture_redacted_screenshot(self, destination):
                destination.write_bytes(b"\x89PNG\r\n\x1a\n")
                return destination.name

            def close(self):
                return None

        with mock.patch.dict(os.environ, {"ACCESS_TRACE_MAX_SITE_PAGES": "0"}), mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", SiteBrowser
        ):
            completed = execute_assessment(run, self.run_directory)

        self.assertEqual([page_two, page_three], visited, (completed["observations"][-1]["url"], completed["observations"][-1]["coverage"]))
        self.assertEqual("COMPLETED", completed["status"])
        self.assertEqual(3, completed["stoppingPoint"]["coverage"]["areasObserved"])
        self.assertEqual("completed", completed["stoppingPoint"]["coverage"]["status"])

        visited.clear()
        page_only_run = create_run(
            {"targetUrl": target, "pageOnly": True}, self.server.server_port
        )
        discovery_count = len(discovered)
        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", SiteBrowser
        ):
            page_only_completed = execute_assessment(page_only_run, self.run_directory)
        self.assertEqual([], visited)
        self.assertEqual(discovery_count, len(discovered))
        self.assertEqual(1, page_only_completed["stoppingPoint"]["coverage"]["areasObserved"])

    def test_site_page_limit_is_developer_configurable_and_zero_means_uncapped(self):
        with mock.patch.dict(os.environ, {"ACCESS_TRACE_MAX_SITE_PAGES": "7"}):
            self.assertEqual(7, configured_site_page_limit())
        with mock.patch.dict(os.environ, {"ACCESS_TRACE_MAX_SITE_PAGES": "0"}):
            self.assertEqual(0, configured_site_page_limit())

    def test_whole_site_continues_to_linked_pages_after_focus_traversal_stalls(self):
        target = self.base_url + "/docs/demos/fixed/index.html"
        linked = self.base_url + "/docs/demos/fixed/linked.html"
        run = create_run({"targetUrl": target, "sitePageLimit": 2}, self.server.server_port)
        visited = []

        class StalledBrowser:
            def __init__(self, target_url):
                self.url = target_url

            def observe(self):
                return {
                    "url": self.url,
                    "title": "Site page",
                    "focus": {"role": "document", "stableId": "document", "isStable": True},
                    "controls": [{"role": "link", "stableId": "link-one", "focusable": True}],
                    "controlCount": 1,
                    "pageContentVisible": True,
                    "lifecycle": {
                        "pageOpen": True, "dialogOpen": False, "dialogObserved": False,
                        "popupObserved": False, "popupAttempted": False, "crashed": False,
                        "offLoopbackRedirect": False, "navigationRedirect": False,
                        "browserLoadError": False, "pageContentVisible": True,
                        "headfulFallback": False,
                    },
                }

            def press_key(self, key):
                pass

            def discover_site_links(self):
                return [linked]

            def navigate_to(self, url):
                visited.append(url)
                self.url = url

            def capture_redacted_screenshot(self, destination):
                destination.write_bytes(b"\x89PNG\r\n\x1a\n")
                return destination.name

            def close(self):
                return None

        with mock.patch("access_trace.journey.IsolatedKeyboardBrowser", StalledBrowser):
            completed = execute_assessment(run, self.run_directory)

        self.assertEqual([linked], visited)
        self.assertEqual("COMPLETED", completed["status"])
        self.assertEqual(2, completed["stoppingPoint"]["coverage"]["areasObserved"])
        self.assertEqual("partial", completed["stoppingPoint"]["coverage"]["status"])

    def test_local_site_traversal_allows_only_documents_inside_the_uploaded_site(self):
        target = "http://127.0.0.1:4173/sites/0123456789abcdef0123456789abcdef/index.html"
        frame_id = "main-frame"
        policy = _UploadedPageRequestPolicy(
            None, target, frame_id, allow_site_documents=True
        )
        policy.initial_document_allowed = True

        self.assertTrue(policy._allows_request(
            "http://127.0.0.1:4173/sites/0123456789abcdef0123456789abcdef/about.html",
            "GET", "Document", frame_id,
        ))
        self.assertFalse(policy._allows_request(
            "http://127.0.0.1:4173/sites/0123456789abcdef0123456789abcdef/../other.html",
            "GET", "Document", frame_id,
        ))
        self.assertFalse(policy._allows_request(
            "http://example.test/about.html", "GET", "Document", frame_id,
        ))
        self.assertFalse(policy._allows_request(
            "http://127.0.0.1:4173/sites/0123456789abcdef0123456789abcdef/about.html",
            "POST", "Document", frame_id,
        ))

    def test_whole_site_continues_after_a_website_action_makes_no_progress(self):
        class WholeSitePlanner:
            attempted_noop = False

            def next_action(self, context):
                if not self.attempted_noop:
                    self.attempted_noop = True
                    return {"kind": "key", "key": "ArrowLeft"}
                if context["coverage"]["status"] == "completed":
                    return {"kind": "complete"}
                return {"kind": "key", "key": "Tab"}

        self.server.planner_factory = WholeSitePlanner
        _, created = self.request(
            "POST",
            "/api/runs",
            {"targetUrl": self.base_url + "/demo/fixed"},
        )

        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", DeterministicContactBrowser
        ):
            status, completed = self.request(
                "POST", "/api/runs/{0}/execute".format(created["id"]), timeout=30
            )

        self.assertEqual(200, status)
        self.assertEqual("COMPLETED", completed["status"])
        self.assertIn(
            {"kind": "website-action-failure", "sequence": 1, "action": "key", "key": "ArrowLeft"},
            completed["warnings"],
        )
        self.assertIn(
            {"kind": "website-action-failure", "sequence": 1, "action": "key", "key": "ArrowLeft"},
            completed["observations"][1]["warnings"],
        )

    def test_unsupported_goal_runs_with_goal_context_and_finishes_inconclusively(self):
        planner_contexts = []

        class UnsupportedGoalPlanner:
            def next_action(self, context):
                planner_contexts.append(context)
                return {"kind": "complete"}

        self.server.planner_factory = UnsupportedGoalPlanner
        goal = "Export the private customer list"
        _, created = self.request(
            "POST",
            "/api/runs",
            {"targetUrl": self.base_url + "/demo/fixed", "goal": goal},
        )

        status, result = self.request(
            "POST", "/api/runs/{0}/execute".format(created["id"]), timeout=30
        )

        self.assertEqual(200, status)
        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertEqual(goal, result["goal"])
        self.assertIsNone(result["successCondition"])
        self.assertEqual(goal, result["observations"][-1]["goalProgress"]["goal"])
        self.assertEqual("unsupported", result["observations"][-1]["goalProgress"]["status"])
        self.assertIn({"kind": "unsupported-goal"}, result["warnings"])
        self.assertEqual(goal, planner_contexts[0]["goal"])
        self.assertEqual("goal-focused", planner_contexts[0]["assessmentScope"])
        self.assertIsNone(planner_contexts[0]["successCondition"])

    def test_unsupported_goal_keeps_its_terminal_context_after_browser_failure(self):
        goal = "Export the private customer list"
        run = create_run(
            {"targetUrl": self.base_url + "/demo/fixed", "goal": goal},
            self.server.server_port,
        )
        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser",
            side_effect=BrowserError("browser unavailable"),
        ):
            result = execute_assessment(run, self.run_directory, planner=mock.Mock())

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertIsNone(result["stoppingPoint"]["successCondition"])
        self.assertEqual(goal, result["stoppingPoint"]["goalProgress"]["goal"])
        self.assertEqual("unsupported", result["stoppingPoint"]["goalProgress"]["status"])

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

    def test_run_exposes_a_versioned_report_ready_evidence_handoff(self):
        _, created = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
        )

        handoff = created["evidenceHandoff"]

        self.assertEqual("access-trace.evidence.v1", handoff["schema"])
        self.assertEqual(created["id"], handoff["runId"])
        self.assertEqual(
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "targetVersion": "fixed",
                "assessmentScope": "goal-focused",
                "goal": "Submit the contact form",
                "successCondition": "Message sent",
                "simulationMode": True,
                "interactionProfile": "keyboard-only",
            },
            handoff["assessment"],
        )
        self.assertEqual("IN_PROGRESS", handoff["terminal"]["status"])
        self.assertEqual(1, len(handoff["observations"]))
        self.assertEqual(1, len(handoff["focusObservations"]))
        self.assertEqual([], handoff["actions"])
        self.assertIsNone(handoff["observations"][0]["focus"]["acceptedInput"])
        self.assertIsNone(handoff["observations"][0]["controls"][0]["acceptedInput"])
        self.assertEqual(
            [{"kind": "observation", "sequence": 1}],
            handoff["evidenceReferences"],
        )
        self.assertFalse(handoff["privacy"]["rawValuesRetained"])
        self.assertFalse(handoff["privacy"]["pasteDataRetained"])
        self.assertFalse(handoff["privacy"]["pageSourceRetained"])
        self.assertIsNone(handoff["reporting"]["explanation"])
        self.assertIsNone(handoff["reporting"]["proposedFix"])
        self.assertIsNone(handoff["reporting"]["confidence"])
        self.assertEqual(
            {
                "assessmentScope": "goal-focused",
                "goal": "Submit the contact form",
                "successCondition": "Message sent",
                "simulationMode": True,
                "interactionProfile": "keyboard-only",
            },
            handoff["comparison"]["settings"],
        )
        self.assertEqual(1, handoff["comparison"]["runCount"])
        serialized = json.dumps(handoff)
        self.assertNotIn("Avery Example", serialized)
        self.assertNotIn("avery@example.test", serialized)
        self.assertNotIn("A fictional message", serialized)

    def test_completed_handoff_keeps_ordered_redacted_evidence_and_stopping_reference(self):
        _, created = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
        )

        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", DeterministicContactBrowser
        ):
            _, completed = self.request(
                "POST", "/api/runs/{0}/execute".format(created["id"]), timeout=30
            )

        handoff = completed["evidenceHandoff"]
        self.assertEqual("COMPLETED", handoff["terminal"]["status"])
        self.assertEqual(completed["interactionCount"], handoff["interactionCount"])
        self.assertEqual(len(completed["actions"]), len(handoff["actions"]))
        self.assertEqual(len(completed["observations"]), len(handoff["observations"]))
        self.assertEqual(
            "name", handoff["actions"][0]["focusAfter"]["stableId"]
        )
        self.assertEqual(
            "name", handoff["actions"][1]["focusBefore"]["stableId"]
        )
        controls = {
            control["stableId"]: control
            for control in handoff["observations"][-1]["controls"]
            if control.get("stableId") in {"name", "email", "message"}
        }
        self.assertEqual({"name", "email", "message"}, set(controls))
        self.assertTrue(all(controls[field]["acceptedInput"] for field in controls))
        self.assertTrue(all(controls[field]["characterCount"] > 0 for field in controls))
        self.assertTrue(all(controls[field]["validationState"] == "valid" for field in controls))
        self.assertTrue(handoff["stopping"]["point"]["successMatched"])
        self.assertEqual(
            completed["stoppingScreenshotRef"],
            handoff["stopping"]["screenshotRef"],
        )
        self.assertIn(
            {
                "kind": "stopping-screenshot",
                "ref": completed["stoppingScreenshotRef"],
                "redacted": True,
            },
            handoff["evidenceReferences"],
        )
        self.assertTrue(handoff["privacy"]["stoppingScreenshotRedacted"])
        self.assertEqual(
            completed,
            json.loads((self.run_directory / (created["id"] + ".json")).read_text()),
        )
        serialized = json.dumps(handoff)
        self.assertNotIn("Avery Example", serialized)
        self.assertNotIn("avery@example.test", serialized)
        self.assertNotIn("A fictional message", serialized)

    def test_blocked_handoff_keeps_recovery_and_terminal_context(self):
        _, created = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/broken",
                "goal": "Submit the contact form",
                "simulationMode": False,
            },
        )

        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", DeterministicContactBrowser
        ):
            _, blocked = self.request(
                "POST", "/api/runs/{0}/execute".format(created["id"]), timeout=30
            )

        handoff = blocked["evidenceHandoff"]
        self.assertEqual("BLOCKED", handoff["terminal"]["status"])
        self.assertEqual(
            "verified", handoff["terminal"]["browserSession"]["cleanup"]["status"]
        )
        self.assertTrue(
            handoff["terminal"]["browserSession"]["cleanup"]["profileRemoved"]
        )
        self.assertEqual(
            blocked["stoppingScreenshotRef"], handoff["stopping"]["screenshotRef"]
        )
        self.assertIn(
            {
                "kind": "stopping-screenshot",
                "ref": blocked["stoppingScreenshotRef"],
                "redacted": True,
            },
            handoff["evidenceReferences"],
        )
        self.assertTrue(handoff["privacy"]["stoppingScreenshotRedacted"])
        self.assertEqual(
            blocked["recoveryEvidence"], handoff["terminal"]["recoveryEvidence"]
        )
        self.assertEqual("submit", handoff["stopping"]["point"]["focus"]["stableId"])
        self.assertFalse(handoff["stopping"]["point"]["successMatched"])
        self.assertEqual(False, handoff["assessment"]["simulationMode"])
        self.assertEqual(
            {
                "assessmentScope": "goal-focused",
                "goal": "Submit the contact form",
                "successCondition": "Message sent",
                "simulationMode": False,
                "interactionProfile": "keyboard-only",
            },
            handoff["comparison"]["settings"],
        )
        serialized = json.dumps(handoff)
        self.assertNotIn("Avery Example", serialized)
        self.assertNotIn("avery@example.test", serialized)
        self.assertNotIn("A fictional message", serialized)

    def test_agent_failed_handoff_keeps_agent_context_separate_from_browser_failure(self):
        class FailingPlanner:
            def next_action(self, context):
                raise PlannerError("planner unavailable")

        self.server.planner_factory = FailingPlanner
        _, created = self.request(
            "POST",
            "/api/runs",
            {"targetUrl": self.base_url + "/demo/fixed"},
        )

        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", DeterministicContactBrowser
        ):
            _, result = self.request(
                "POST", "/api/runs/{0}/execute".format(created["id"]), timeout=30
            )

        handoff = result["evidenceHandoff"]
        self.assertEqual("INCONCLUSIVE", handoff["terminal"]["status"])
        self.assertEqual("planner-failure", handoff["terminal"]["agentFailure"]["kind"])
        self.assertIsNone(handoff["terminal"]["browserFailure"])
        self.assertEqual("whole-site", handoff["assessment"]["assessmentScope"])
        self.assertIsNone(handoff["assessment"]["goal"])
        self.assertIsNone(handoff["progress"]["goal"])

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
            "POST", "/api/runs/{0}/execute".format(created["id"]), timeout=30
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

    def test_broken_contact_goal_classifies_a_repeatable_submit_barrier(self):
        _, created = self.request(
            "POST",
            "/api/runs",
            {
                "targetUrl": self.base_url + "/demo/broken",
                "goal": "Submit the contact form",
            },
        )

        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", DeterministicContactBrowser
        ):
            status, blocked = self.request(
                "POST", "/api/runs/{0}/execute".format(created["id"]), timeout=10
            )

        self.assertEqual(200, status)
        self.assertEqual("BLOCKED", blocked["status"])
        self.assertEqual("verified", blocked["browserSession"]["cleanup"]["status"])
        self.assertTrue(blocked["browserSession"]["cleanup"]["profileRemoved"])
        self.assertIsNone(blocked["browserFailure"])
        self.assertIsNone(blocked["agentFailure"])
        self.assertEqual("Submit", blocked["stoppingPoint"]["focus"]["accessibleName"])
        self.assertFalse(blocked["stoppingPoint"]["successMatched"])
        self.assertEqual("Message sent", blocked["stoppingPoint"]["successCondition"])

        submit_actions = [
            action
            for action in blocked["actions"]
            if action["focusBefore"].get("stableId") == "submit"
            and action["key"] in {"Enter", "Space"}
        ]
        self.assertEqual(
            ["Enter", "Space"],
            [action["key"] for action in submit_actions],
        )
        self.assertTrue(all(action["status"] == "delivered" for action in submit_actions))
        self.assertEqual(1, len(blocked["recoveryEvidence"]))
        self.assertEqual(
            {"Tab", "Shift+Tab"},
            {step["key"] for step in blocked["recoveryEvidence"][0]["actions"]},
        )
        self.assertTrue(blocked["recoveryEvidence"][0]["unchangedProgress"])
        self.assertTrue(blocked["recoveryEvidence"][0]["sameSubmitFocus"])
        self.assertTrue(blocked["recoveryEvidence"][0]["localFocusRecovery"])
        self.assertFalse(blocked["recoveryEvidence"][0]["wholePageWrapped"])
        self.assertEqual(len(blocked["actions"]) + 1, len(blocked["observations"]))
        self.assertNotIn("Escape", [action.get("key") for action in blocked["actions"]])
        self.assertEqual("submit", blocked["observations"][-1]["focus"]["stableId"])

        screenshot = self.run_directory / blocked["stoppingScreenshotRef"]
        self.assertTrue(screenshot.is_file())
        self.assertTrue(screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(blocked["interactionCount"], len(blocked["actions"]))
        self.assertEqual(blocked, json.loads((self.run_directory / (created["id"] + ".json")).read_text()))

        serialized = json.dumps(blocked)
        self.assertNotIn("Avery Example", serialized)
        self.assertNotIn("avery@example.test", serialized)
        self.assertNotIn("A fictional message", serialized)

    def test_barrier_probe_retries_one_failed_delivery_before_classifying_the_barrier(self):
        class BarrierRetryBrowser:
            def __init__(self, target_url):
                self.target_url = target_url
                self.focus = "submit"
                self.failed_enter = False

            def observe(self):
                if self.focus == "submit":
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
                        "accessibleName": "Message",
                        "tag": "textarea",
                        "stableId": "message",
                        "isStable": True,
                        "characterCount": 16,
                        "acceptedInput": True,
                        "validationState": "valid",
                    }
                return {
                    "url": self.target_url,
                    "title": "AccessTrace Contact form",
                    "focus": focus,
                    "controls": [
                        {
                            "role": "textbox",
                            "accessibleName": field.title(),
                            "tag": "textarea" if field == "message" else "input",
                            "stableId": field,
                            "focusable": True,
                            "isStable": True,
                            "characterCount": 16,
                            "acceptedInput": True,
                            "validationState": "valid",
                        }
                        for field in ("name", "email", "message")
                    ]
                    + [
                        {
                            "role": "button",
                            "accessibleName": "Submit",
                            "tag": "button",
                            "stableId": "submit",
                            "focusable": True,
                            "isStable": True,
                        }
                    ],
                    "successMatched": False,
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def press_key(self, key):
                if key == "Enter" and not self.failed_enter:
                    self.failed_enter = True
                    raise BrowserActionError("temporary barrier probe failure")
                if key == "Shift+Tab":
                    self.focus = "message"
                elif key == "Tab":
                    self.focus = "submit"

            def capture_redacted_screenshot(self, destination):
                destination.write_bytes(b"\x89PNG\r\n\x1a\n")
                return destination.name

            def close(self):
                return None

        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/broken",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", BarrierRetryBrowser
        ):
            result = execute_contact_goal(run, self.run_directory, planner=mock.Mock())

        self.assertEqual("BLOCKED", result["status"])
        self.assertIsNone(result["browserFailure"])
        enter_actions = [
            action for action in result["actions"] if action.get("key") == "Enter"
        ]
        self.assertEqual(["failed", "delivered"], [action["status"] for action in enter_actions])
        self.assertEqual(
            ["Enter", "Space"], result["recoveryEvidence"][0]["attemptedActivations"]
        )

    def test_barrier_probe_focus_drift_cannot_complete_or_block_the_run(self):
        class FocusDriftBrowser:
            def __init__(self, target_url):
                self.target_url = target_url
                self.focus = "submit"
                self.failed_enter = False
                self.success = False

            def observe(self):
                if self.focus == "submit":
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
                        "accessibleName": "Message",
                        "tag": "textarea",
                        "stableId": "message",
                        "isStable": True,
                        "characterCount": 16,
                        "acceptedInput": True,
                        "validationState": "valid",
                    }
                return {
                    "url": self.target_url,
                    "title": "AccessTrace Contact form",
                    "focus": focus,
                    "controls": [
                        {
                            "role": "textbox",
                            "accessibleName": field.title(),
                            "tag": "textarea" if field == "message" else "input",
                            "stableId": field,
                            "focusable": True,
                            "isStable": True,
                            "characterCount": 16,
                            "acceptedInput": True,
                            "validationState": "valid",
                        }
                        for field in ("name", "email", "message")
                    ]
                    + [
                        {
                            "role": "button",
                            "accessibleName": "Submit",
                            "tag": "button",
                            "stableId": "submit",
                            "focusable": True,
                            "isStable": True,
                        }
                    ],
                    "successMatched": self.success,
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def press_key(self, key):
                if key == "Enter" and not self.failed_enter:
                    self.failed_enter = True
                    self.focus = "message"
                    raise BrowserActionError("focus drift during barrier probe")
                if key == "Enter":
                    self.focus = "submit"
                elif key == "Space":
                    self.success = True
                elif key == "Shift+Tab":
                    self.focus = "message"
                elif key == "Tab":
                    self.focus = "submit"

            def capture_redacted_screenshot(self, destination):
                destination.write_bytes(b"\x89PNG\r\n\x1a\n")
                return destination.name

            def close(self):
                return None

        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/broken",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", FocusDriftBrowser
        ):
            result = execute_contact_goal(run, self.run_directory, planner=mock.Mock())

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertIsNone(result["browserFailure"])
        self.assertTrue(result["observations"][-1]["success"]["matched"])
        self.assertFalse(result["recoveryEvidence"][0]["activationFocusConsistent"])
        self.assertEqual("submit", result["stoppingPoint"]["focus"]["stableId"])
        self.assertIsNone(result["stoppingScreenshotRef"])

    def test_missing_lifecycle_evidence_cannot_preserve_a_successful_observation(self):
        class MissingLifecycleBrowser:
            def __init__(self, target_url):
                self.target_url = target_url
                self.success = False

            def observe(self):
                observation = {
                    "url": self.target_url,
                    "title": "AccessTrace Contact form",
                    "focus": {
                        "role": "button",
                        "accessibleName": "Submit",
                        "tag": "button",
                        "stableId": "submit",
                        "isStable": True,
                    },
                    "controls": [
                        {
                            "role": "textbox",
                            "accessibleName": field.title(),
                            "tag": "textarea" if field == "message" else "input",
                            "stableId": field,
                            "focusable": True,
                            "isStable": True,
                            "characterCount": 16,
                            "acceptedInput": True,
                            "validationState": "valid",
                        }
                        for field in ("name", "email", "message")
                    ]
                    + [
                        {
                            "role": "button",
                            "accessibleName": "Submit",
                            "tag": "button",
                            "stableId": "submit",
                            "focusable": True,
                            "isStable": True,
                        }
                    ],
                    "successMatched": self.success,
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }
                if self.success:
                    observation["lifecycle"] = None
                return observation

            def press_key(self, key):
                if key == "Enter":
                    self.success = True

            def close(self):
                return None

        class SubmitPlanner:
            def next_action(self, context):
                return {"kind": "key", "key": "Enter"}

        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", MissingLifecycleBrowser
        ):
            result = execute_fixed_goal(
                run, self.run_directory, planner=SubmitPlanner()
            )

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertTrue(result["observations"][-1]["success"]["matched"])
        self.assertEqual("invalid", result["observations"][-1]["lifecycle"]["evidence"])
        self.assertEqual({"kind": "browser-failure"}, result["browserFailure"])
        self.assertIsNone(result["stoppingScreenshotRef"])

    def test_page_wrap_and_generic_no_progress_do_not_become_blocked(self):
        class WrappingBrowser:
            def __init__(self, target_url):
                self.target_url = target_url

            def observe(self):
                return {
                    "url": self.target_url,
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
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def press_key(self, key):
                return None

            def close(self):
                return None

        class NoProgressPlanner:
            def next_action(self, context):
                return {"kind": "key", "key": "Tab"}

        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/broken",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch("access_trace.journey.IsolatedKeyboardBrowser", WrappingBrowser):
            result = execute_contact_goal(
                run,
                self.run_directory,
                planner=NoProgressPlanner(),
            )

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertEqual([], result["recoveryEvidence"])
        self.assertNotEqual("BLOCKED", result["status"])

    def test_submit_recovery_that_wraps_the_page_is_not_a_barrier(self):
        class WrapAroundSubmitBrowser:
            def __init__(self, target_url):
                self.target_url = target_url
                self.focus = "submit"

            def observe(self):
                if self.focus == "submit":
                    focus = {
                        "role": "button",
                        "accessibleName": "Submit",
                        "tag": "button",
                        "stableId": "submit",
                        "isStable": True,
                    }
                else:
                    focus = {
                        "role": "document",
                        "accessibleName": "Fictional contact form",
                        "tag": "body",
                        "stableId": "document",
                        "isStable": True,
                    }
                return {
                    "url": self.target_url,
                    "title": "AccessTrace Contact form",
                    "focus": focus,
                    "controls": [],
                    "successMatched": False,
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def press_key(self, key):
                if key == "Shift+Tab":
                    self.focus = "document"
                elif key == "Tab":
                    self.focus = "submit"

            def close(self):
                return None

        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/broken",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", WrapAroundSubmitBrowser
        ):
            result = execute_contact_goal(
                run,
                self.run_directory,
                planner=mock.Mock(),
            )

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertTrue(result["recoveryEvidence"][0]["wholePageWrapped"])

    def test_unexpected_space_success_is_terminal_and_verified(self):
        class SpaceSuccessBrowser:
            def __init__(self, target_url):
                self.target_url = target_url
                self.success = False

            def observe(self):
                return {
                    "url": self.target_url,
                    "title": "AccessTrace Contact form",
                    "focus": {
                        "role": "button",
                        "accessibleName": "Submit",
                        "tag": "button",
                        "stableId": "submit",
                        "isStable": True,
                    },
                    "controls": [
                        {
                            "role": "textbox",
                            "accessibleName": "Message",
                            "tag": "textarea",
                            "stableId": "message",
                            "focusable": True,
                        },
                        {
                            "role": "button",
                            "accessibleName": "Submit",
                            "tag": "button",
                            "stableId": "submit",
                            "focusable": True,
                        },
                    ],
                    "successMatched": self.success,
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def press_key(self, key):
                if key == "Space":
                    self.success = True

            def capture_redacted_screenshot(self, destination):
                destination.write_bytes(b"\x89PNG\r\n\x1a\n")
                return destination.name

            def close(self):
                return None

        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/broken",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch(
            "access_trace.journey.IsolatedKeyboardBrowser", SpaceSuccessBrowser
        ):
            result = execute_contact_goal(
                run,
                self.run_directory,
                planner=mock.Mock(),
            )

        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual("Space", result["actions"][-1]["key"])
        self.assertIsNotNone(result["stoppingPoint"])

    def test_escapable_dialog_is_recovered_but_not_called_a_barrier(self):
        class DialogBrowser:
            def __init__(self, target_url):
                self.target_url = target_url
                self.focus = "document"
                self.dialog_open = False

            def observe(self):
                if self.focus == "submit":
                    focus = {
                        "role": "button",
                        "accessibleName": "Submit",
                        "tag": "button",
                        "stableId": "submit",
                        "isStable": True,
                    }
                else:
                    focus = {
                        "role": "document",
                        "accessibleName": "Fictional contact form",
                        "tag": "body",
                        "stableId": "document",
                        "isStable": True,
                    }
                return {
                    "url": self.target_url,
                    "title": "AccessTrace Contact form",
                    "focus": focus,
                    "controls": [],
                    "successMatched": False,
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": self.dialog_open,
                        "dialogObserved": self.dialog_open,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def press_key(self, key):
                if key == "Tab" and not self.dialog_open:
                    self.focus = "submit" if self.focus == "document" else "document"
                elif key == "Shift+Tab" and not self.dialog_open:
                    self.focus = "submit" if self.focus == "document" else "document"
                elif key in {"Enter", "Space"} and self.focus == "submit":
                    self.dialog_open = True
                elif key == "Escape":
                    self.dialog_open = False

            def close(self):
                return None

        class ReachSubmitPlanner:
            def next_action(self, context):
                return {"kind": "key", "key": "Tab"}

        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/broken",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch("access_trace.journey.IsolatedKeyboardBrowser", DialogBrowser):
            result = execute_contact_goal(
                run,
                self.run_directory,
                planner=ReachSubmitPlanner(),
            )

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertNotEqual("BLOCKED", result["status"])
        self.assertGreaterEqual(
            [action["key"] for action in result["actions"]].count("Escape"), 1
        )
        self.assertIn("Tab", [action["key"] for action in result["actions"]])
        self.assertIn("Shift+Tab", [action["key"] for action in result["actions"]])

    def test_planner_timeout_does_not_become_blocked(self):
        class StableBrowser:
            def __init__(self, target_url):
                self.target_url = target_url

            def observe(self):
                return {
                    "url": self.target_url,
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
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def close(self):
                return None

        class TimeoutPlanner:
            calls = 0

            def next_action(self, context):
                self.calls += 1
                raise PlannerError("planner timed out")

        planner = TimeoutPlanner()
        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/broken",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch("access_trace.journey.IsolatedKeyboardBrowser", StableBrowser):
            result = execute_contact_goal(
                run,
                self.run_directory,
                planner=planner,
            )

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertNotEqual("BLOCKED", result["status"])
        self.assertEqual("planner-failure", result["agentFailure"]["kind"])
        self.assertEqual(2, planner.calls)
        self.assertEqual(2, result["agentFailure"]["attempts"])

    def test_invalid_planner_decision_is_retried_against_the_same_observation(self):
        class StableBrowser:
            def __init__(self, target_url):
                self.target_url = target_url

            def observe(self):
                return {
                    "url": self.target_url,
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
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def close(self):
                return None

        class InvalidPlanner:
            def __init__(self):
                self.contexts = []

            def next_action(self, context):
                self.contexts.append(context)
                return {"kind": "click", "selector": "#submit"}

        planner = InvalidPlanner()
        run = create_run(
            {
                "targetUrl": self.base_url + "/demo/fixed",
                "goal": "Submit the contact form",
            },
            self.server.server_port,
        )
        with mock.patch("access_trace.journey.IsolatedKeyboardBrowser", StableBrowser):
            result = execute_contact_goal(run, self.run_directory, planner=planner)

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertEqual(2, len(planner.contexts))
        self.assertEqual(planner.contexts[0], planner.contexts[1])
        self.assertEqual(2, result["agentFailure"]["attempts"])
        self.assertIsNone(result["browserFailure"])

    def test_one_action_delivery_failure_reobserves_and_allows_the_journey_to_continue(self):
        class FlakyBrowser:
            def __init__(self, target_url):
                self.target_url = target_url
                self.focus = "document"
                self.failed_once = False

            def observe(self):
                focus = (
                    {
                        "role": "button",
                        "accessibleName": "Submit",
                        "tag": "button",
                        "stableId": "submit",
                        "isStable": True,
                    }
                    if self.focus == "submit"
                    else {
                        "role": "document",
                        "accessibleName": "Fictional contact form",
                        "tag": "body",
                        "stableId": "document",
                        "isStable": True,
                    }
                )
                return {
                    "url": self.target_url,
                    "title": "AccessTrace Contact form",
                    "focus": focus,
                    "controls": [
                        {
                            "role": "button",
                            "accessibleName": "Submit",
                            "tag": "button",
                            "stableId": "submit",
                            "focusable": True,
                            "isStable": True,
                        }
                    ],
                    "successMatched": False,
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def press_key(self, key):
                if key == "Tab" and not self.failed_once:
                    self.failed_once = True
                    raise BrowserActionError("temporary input failure")
                if key == "Tab":
                    self.focus = "submit"

            def capture_redacted_screenshot(self, destination):
                destination.write_bytes(b"\x89PNG\r\n\x1a\n")
                return destination.name

            def close(self):
                return None

        class WholeSitePlanner:
            def next_action(self, context):
                if context["coverage"]["completed"]:
                    return {"kind": "complete"}
                return {"kind": "key", "key": "Tab"}

        run = create_run(
            {"targetUrl": self.base_url + "/demo/fixed"}, self.server.server_port
        )
        with mock.patch("access_trace.journey.IsolatedKeyboardBrowser", FlakyBrowser):
            result = execute_assessment(
                run, self.run_directory, planner=WholeSitePlanner()
            )

        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual(["failed", "delivered"], [action["status"] for action in result["actions"]])
        self.assertIn(
            {"kind": "action-delivery-failure", "sequence": 1, "action": "key", "key": "Tab"},
            result["warnings"],
        )
        self.assertIsNone(result["browserFailure"])
        self.assertIsNone(result["agentFailure"])

    def test_repeated_action_delivery_failure_is_inconclusive_and_not_an_agent_failure(self):
        class FailingBrowser:
            def __init__(self, target_url):
                self.target_url = target_url

            def observe(self):
                return {
                    "url": self.target_url,
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
                    "lifecycle": {
                        "pageOpen": True,
                        "dialogOpen": False,
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
                }

            def press_key(self, key):
                raise BrowserActionError("input is unavailable")

            def close(self):
                return None

        class TabPlanner:
            def next_action(self, context):
                return {"kind": "key", "key": "Tab"}

        run = create_run(
            {"targetUrl": self.base_url + "/demo/fixed"}, self.server.server_port
        )
        with mock.patch("access_trace.journey.IsolatedKeyboardBrowser", FailingBrowser):
            result = execute_assessment(run, self.run_directory, planner=TabPlanner())

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertEqual(
            {"kind": "action-delivery-failure", "attempts": 2},
            result["browserFailure"],
        )
        self.assertIsNone(result["agentFailure"])
        self.assertEqual(2, len(result["actions"]))

    def test_lifecycle_warnings_are_retained_and_closed_pages_are_inconclusive(self):
        class ClosedBrowser:
            def __init__(self, target_url):
                self.target_url = target_url

            def observe(self):
                return {
                    "url": self.target_url,
                    "title": "AccessTrace Contact form",
                    "focus": {},
                    "controls": [],
                    "successMatched": False,
                    "lifecycle": {
                        "pageOpen": False,
                        "dialogOpen": True,
                        "dialogObserved": True,
                        "popupObserved": True,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
                    },
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
        with mock.patch("access_trace.journey.IsolatedKeyboardBrowser", ClosedBrowser):
            result = execute_contact_goal(run, self.run_directory, planner=mock.Mock())

        self.assertEqual("INCONCLUSIVE", result["status"])
        self.assertIn({"kind": "dialog-open"}, result["warnings"])
        self.assertIn({"kind": "popup-observed"}, result["warnings"])
        self.assertIn({"kind": "page-closed"}, result["warnings"])
        self.assertEqual({"kind": "browser-failure"}, result["browserFailure"])
        self.assertIsNone(result["agentFailure"])

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
        process = FakeCodexProcess(
            codex_output(
                {"kind": "type", "key": None, "field": "name", "text": "fictional"}
            )
        )
        with mock.patch("access_trace.planner.subprocess.Popen", return_value=process):
            with self.assertRaises(PlannerError):
                CodexPlanner(executable="fake-codex").next_action(context)

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

    def test_codex_planner_reports_saved_login_errors_without_real_processes(self):
        process = FakeCodexProcess(
            b"",
            returncode=1,
            stderr=b"Not logged in. Run codex login.",
        )
        with mock.patch("access_trace.planner.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(PlannerError, "codex login"):
                CodexPlanner(executable="fake-codex").next_action(
                    {"pageEvidence": {"focus": {}}}
                )

    def test_codex_planner_reports_spawn_errors_without_running_a_process(self):
        with mock.patch(
            "access_trace.planner.subprocess.Popen",
            side_effect=FileNotFoundError("codex executable is missing"),
        ) as spawn:
            with self.assertRaisesRegex(PlannerError, "could not start"):
                CodexPlanner(executable="missing-codex").next_action(
                    {"pageEvidence": {"focus": {}}}
                )
        spawn.assert_called_once()

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

        def run_fake(action, target_context):
            process = FakeCodexProcess(codex_output(action))
            with mock.patch(
                "access_trace.planner.subprocess.Popen", return_value=process
            ):
                result = CodexPlanner(executable="fake-codex").next_action(
                    target_context
                )
            return result

        key_action = {"kind": "key", "key": "Tab", "field": None, "text": None}
        self.assertEqual({"kind": "key", "key": "Tab"}, run_fake(key_action, context))

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
        self.assertEqual(
            {"kind": "type", "field": "name", "text": "fictional"},
            run_fake(
                {
                    "kind": "type",
                    "key": None,
                    "field": "name",
                    "text": "fictional",
                },
                type_context,
            ),
        )

        with self.assertRaises(PlannerError):
            run_fake(
                {"kind": "click", "key": None, "field": None, "text": None},
                context,
            )

        with self.assertRaises(PlannerError):
            run_fake(
                {
                    "kind": "key",
                    "key": "Tab",
                    "field": None,
                    "text": None,
                    "extra": "rejected",
                },
                context,
            )

    def test_codex_planner_uses_no_tools_minimal_environment_and_bounded_image(self):
        context = {
            "pageEvidence": {
                "untrusted": True,
                "screenshotDataUrl": "data:image/png;base64,"
                + base64.b64encode(b"\x89PNG\r\n\x1a\nredacted").decode("ascii"),
                "focus": {
                    "role": "document",
                    "tag": "body",
                    "stableId": "document",
                    "isStable": True,
                },
            }
        }
        process = FakeCodexProcess(
            codex_output({"kind": "key", "key": "Tab", "field": None, "text": None})
        )
        captured = {}

        def fake_popen(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            schema_path = Path(args[args.index("--output-schema") + 1])
            captured["schema_path"] = schema_path
            captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
            image_argument = next(
                argument for argument in args if argument.startswith("--image=")
            )
            image_path = Path(image_argument.split("=", 1)[1])
            captured["image_path"] = image_path
            captured["image_bytes"] = image_path.read_bytes()
            return process

        environment = {
            "PATH": "/safe/bin",
            "HOME": "/home/test-user",
            "CODEX_HOME": "/home/test-user/.codex",
            "TMPDIR": tempfile.gettempdir(),
            "LANG": "en_US.UTF-8",
            "OPENAI_API_KEY": "api-key-secret",
            "CODEX_API_KEY": "codex-api-key-secret",
            "OPENAI_BASE_URL": "https://api-key-provider.example",
            "HTTPS_PROXY": "https://proxy-token.example",
            "AWS_SECRET_ACCESS_KEY": "cloud-secret",
            "NODE_OPTIONS": "--require /tmp/untrusted.js",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            with mock.patch(
                "access_trace.planner.subprocess.Popen", side_effect=fake_popen
            ) as spawn:
                result = CodexPlanner(executable="codex-test").next_action(context)

        self.assertEqual({"kind": "key", "key": "Tab"}, result)
        spawn.assert_called_once()
        args = captured["args"]
        kwargs = captured["kwargs"]
        self.assertEqual("codex-test", args[0])
        self.assertEqual("exec", args[1])
        self.assertEqual("--json", args[2])
        self.assertIn("--ephemeral", args)
        self.assertIn("--sandbox", args)
        self.assertEqual("read-only", args[args.index("--sandbox") + 1])
        disabled_features = {
            args[index + 1]
            for index, argument in enumerate(args[:-1])
            if argument == "--disable"
        }
        self.assertEqual(set(CODEX_DISABLED_FEATURES), disabled_features)
        self.assertEqual('web_search="disabled"', args[args.index("--config") + 1])
        self.assertFalse(kwargs["shell"])
        self.assertTrue(any(argument.startswith("--image=") for argument in args))
        self.assertTrue(
            args[-1].startswith("You are the autonomous Codex keyboard-journey planner.")
        )
        self.assertNotIn("screenshotDataUrl", args[-1])
        self.assertNotIn(context["pageEvidence"]["screenshotDataUrl"], args[-1])
        self.assertEqual(
            {"PATH", "HOME", "CODEX_HOME", "TMPDIR", "LANG"},
            set(kwargs["env"]),
        )
        self.assertEqual("/home/test-user/.codex", kwargs["env"]["CODEX_HOME"])
        self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
        self.assertNotIn("CODEX_API_KEY", kwargs["env"])
        self.assertNotIn("OPENAI_BASE_URL", kwargs["env"])
        self.assertNotIn("HTTPS_PROXY", kwargs["env"])
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", kwargs["env"])
        self.assertNotIn("NODE_OPTIONS", kwargs["env"])
        self.assertEqual(CODEX_OUTPUT_SCHEMA, captured["schema"])
        self.assertTrue(captured["image_bytes"].startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertLessEqual(
            len(captured["image_bytes"]), MAX_PLANNER_SCREENSHOT_BYTES
        )
        self.assertFalse(captured["image_path"].exists())
        self.assertFalse(captured["schema_path"].exists())

    def test_codex_planner_timeout_and_cancel_terminate_fake_child(self):
        context = {"pageEvidence": {"focus": {"role": "document"}}}
        timeout_process = FakeCodexProcess(codex_output({}), timeout=True)
        with mock.patch(
            "access_trace.planner.subprocess.Popen", return_value=timeout_process
        ):
            with self.assertRaisesRegex(PlannerError, "timed out"):
                CodexPlanner(executable="fake-codex", timeout=0.01).next_action(
                    context
                )
        self.assertTrue(timeout_process.terminated)
        self.assertEqual(2, timeout_process.communicate_calls)

        planner = CodexPlanner(executable="fake-codex")
        cancel_process = FakeCodexProcess(
            codex_output({"kind": "key", "key": "Tab", "field": None, "text": None}),
            on_communicate=planner.cancel,
        )
        with mock.patch(
            "access_trace.planner.subprocess.Popen", return_value=cancel_process
        ):
            with self.assertRaisesRegex(PlannerError, "cancelled"):
                planner.next_action(context)
        self.assertTrue(cancel_process.terminated)

    def test_windows_codex_cmd_shim_is_resolved_to_node(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            shim = directory / "codex.cmd"
            shim.write_text("@echo off\n", encoding="utf-8")
            script = (
                directory
                / "node_modules"
                / "@openai"
                / "codex"
                / "bin"
                / "codex.js"
            )
            script.parent.mkdir(parents=True)
            script.write_text("// fake Codex entrypoint\n", encoding="utf-8")
            path_type = type(Path())
            which = {
                "codex.exe": None,
                "codex": str(shim),
                "node": "/runtime/node.exe",
            }
            with mock.patch("access_trace.planner.os.name", "nt"):
                with mock.patch("access_trace.planner.Path", path_type):
                    with mock.patch.dict(os.environ, {"CODEX_EXECUTABLE": ""}):
                        with mock.patch(
                            "access_trace.planner.shutil.which",
                            side_effect=lambda name: which.get(name),
                        ):
                            self.assertEqual(
                                ["/runtime/node.exe", str(script)], _codex_executable()
                            )

    def test_browser_cleanup_removes_profile_and_reports_failure(self):
        profile = Path(tempfile.mkdtemp())
        (profile / "profile-marker").write_text("temporary")
        browser = object.__new__(IsolatedKeyboardBrowser)
        browser.profile_directory = profile
        browser.process = None
        browser.connection = None
        browser.browser_connection = None

        browser.close()

        self.assertFalse(profile.exists())

        failed_profile = Path(tempfile.mkdtemp())
        failed_browser = object.__new__(IsolatedKeyboardBrowser)
        failed_browser.profile_directory = failed_profile
        failed_browser.process = None
        failed_browser.connection = None
        failed_browser.browser_connection = None
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
                        "dialogObserved": False,
                        "popupObserved": False,
                        "crashed": False,
                        "offLoopbackRedirect": False,
                        "navigationRedirect": False,
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

        self.assertIn('href="/demo/fixed"', landing_page)
        self.assertNotIn("attacker.example", landing_page)

    def raw_request(self, path):
        with urlopen(self.base_url + path, timeout=2) as response:
            return response.status, response.read().decode("utf-8")


if __name__ == "__main__":
    unittest.main()
