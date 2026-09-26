"""Security regression tests for the Codex planner process boundary."""

import io
import json
import subprocess
import unittest
from unittest import mock

from access_trace.planner import CodexPlanner, PlannerError
from access_trace.source_review import CodexSourceReviewer, SourceReviewError


class CapturedStdin(io.BytesIO):
    """CapturedStdin retains bytes after the production writer closes stdin."""

    def close(self):
        """close records the flush without hiding bytes needed by assertions."""
        self.flush()


class NoisyCodexProcess:
    """NoisyCodexProcess exposes pipe streams and records forced termination."""

    def __init__(self, stdout=b"", stderr=b"", timeout=False, on_wait=None):
        self.stdin = CapturedStdin()
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = None
        self.terminated = False
        self.timeout = timeout
        self.on_wait = on_wait

    def communicate(self, timeout=None):
        """communicate provides the legacy unbounded path for the red test."""
        self.returncode = 0
        return self.stdout.read(), self.stderr.read()

    def wait(self, timeout=None):
        """wait exposes the process exit status to bounded stream readers."""
        if self.timeout and not self.terminated:
            raise subprocess.TimeoutExpired("codex", timeout)
        if self.on_wait is not None:
            self.on_wait()
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def poll(self):
        """poll reports the process exit status for cancellation checks."""
        return self.returncode

    def terminate(self):
        """terminate records that the output limit stopped the process."""
        self.terminated = True
        self.returncode = -15

    def kill(self):
        """kill records forced termination when a child ignores terminate."""
        self.terminated = True
        self.returncode = -9


class PlannerOutputSecurityTests(unittest.TestCase):
    """PlannerOutputSecurityTests checks both child output channels are bounded."""

    def test_oversized_stdout_terminates_child(self):
        """test_oversized_stdout_terminates_child prevents unbounded JSONL capture."""
        process = NoisyCodexProcess(stdout=b"x" * 30_000)
        with mock.patch("access_trace.planner.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(PlannerError, "output exceeded"):
                CodexPlanner(executable="fake-codex").next_action({})
        self.assertTrue(process.terminated)

    def test_oversized_stderr_terminates_child(self):
        """test_oversized_stderr_terminates_child bounds diagnostic capture too."""
        process = NoisyCodexProcess(stderr=b"x" * 70_000)
        with mock.patch("access_trace.planner.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(PlannerError, "output exceeded"):
                CodexPlanner(executable="fake-codex").next_action({})
        self.assertTrue(process.terminated)

    def test_planner_prompt_is_sent_through_stdin(self):
        """test_planner_prompt_is_sent_through_stdin keeps page data out of argv."""
        action = {"kind": "complete", "key": None, "field": None, "text": None}
        process = NoisyCodexProcess(stdout=(json.dumps(action) + "\n").encode())
        captured = {}

        def fake_popen(args, **kwargs):
            """fake_popen records public process arguments and stdin mode."""
            captured.update(args=args, kwargs=kwargs)
            return process

        with mock.patch("access_trace.planner.subprocess.Popen", side_effect=fake_popen):
            result = CodexPlanner(executable="fake-codex").next_action(
                {"goal": None, "secretMarker": "private-page-evidence"}
            )
        self.assertEqual({"kind": "complete"}, result)
        self.assertEqual("-", captured["args"][-1])
        self.assertNotIn("private-page-evidence", " ".join(captured["args"]))
        self.assertEqual(subprocess.PIPE, captured["kwargs"]["stdin"])
        self.assertIn(b"private-page-evidence", process.stdin.getvalue())

    def test_source_review_prompt_is_sent_through_stdin(self):
        """test_source_review_prompt_is_sent_through_stdin hides uploaded source."""
        result = {"status": "NO_PATCH", "summary": "No change", "relevantPaths": [], "patch": ""}
        process = NoisyCodexProcess(stdout=(json.dumps(result) + "\n").encode())
        captured = {}

        def fake_popen(args, **kwargs):
            """fake_popen records public process arguments and stdin mode."""
            captured.update(args=args, kwargs=kwargs)
            return process

        with mock.patch("access_trace.source_review.subprocess.Popen", side_effect=fake_popen):
            actual = CodexSourceReviewer(executable="fake-codex")._request(
                "private-uploaded-source"
            )
        self.assertEqual(result, actual)
        self.assertEqual("-", captured["args"][-1])
        self.assertNotIn("private-uploaded-source", " ".join(captured["args"]))
        self.assertEqual(subprocess.PIPE, captured["kwargs"]["stdin"])
        self.assertEqual(b"private-uploaded-source", process.stdin.getvalue())

    def test_planner_timeout_still_terminates_with_stdin_writer(self):
        """test_planner_timeout_still_terminates_with_stdin_writer checks cleanup."""
        process = NoisyCodexProcess(timeout=True)
        with mock.patch("access_trace.planner.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(PlannerError, "timed out"):
                CodexPlanner(executable="fake-codex", timeout=0.01).next_action({})
        self.assertTrue(process.terminated)

    def test_planner_cancel_still_terminates_with_stdin_writer(self):
        """test_planner_cancel_still_terminates_with_stdin_writer checks cancellation."""
        planner = CodexPlanner(executable="fake-codex")
        process = NoisyCodexProcess(on_wait=planner.cancel)
        with mock.patch("access_trace.planner.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(PlannerError, "cancelled"):
                planner.next_action({})
        self.assertTrue(process.terminated)

    def test_source_review_timeout_still_terminates_with_stdin_writer(self):
        """test_source_review_timeout_still_terminates_with_stdin_writer checks cleanup."""
        process = NoisyCodexProcess(timeout=True)
        with mock.patch("access_trace.source_review.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(SourceReviewError, "timed out"):
                CodexSourceReviewer(executable="fake-codex", timeout=0.01)._request("private")
        self.assertTrue(process.terminated)

    def test_source_review_output_limit_still_terminates_child(self):
        """test_source_review_output_limit_still_terminates_child checks output capture."""
        process = NoisyCodexProcess(stdout=b"x" * 170_000)
        with mock.patch("access_trace.source_review.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(SourceReviewError, "output exceeded"):
                CodexSourceReviewer(executable="fake-codex")._request("private")
        self.assertTrue(process.terminated)

    def test_source_review_cancel_still_terminates_child(self):
        """test_source_review_cancel_still_terminates_child checks cancellation."""
        reviewer = CodexSourceReviewer(executable="fake-codex")
        process = NoisyCodexProcess(on_wait=reviewer.cancel)
        with mock.patch("access_trace.source_review.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(SourceReviewError, "cancelled"):
                reviewer._request("private")
        self.assertTrue(process.terminated)


if __name__ == "__main__":
    unittest.main()
