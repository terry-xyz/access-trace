import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

from access_trace.server import create_server


class FakeReviewer:
    def review(self, run, context):
        return {
            "status": "PATCH_READY",
            "summary": "Connect the label to its field.",
            "rootCause": "The input has no associated label.",
            "proposedFix": "Add a matching id and for attribute.",
            "relevantPaths": ["index.html"],
            "patch": (
                "diff --git a/index.html b/index.html\n"
                "--- a/index.html\n+++ b/index.html\n"
                "@@ -1 +1 @@\n"
                "-<label>Email</label><input>\n"
                "+<label for=\"email\">Email</label><input id=\"email\">\n"
            ),
        }


class SourceReviewApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.server = create_server(
            "127.0.0.1", 0, Path(self.temporary.name), source_reviewer_factory=FakeReviewer
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.run_id = str(uuid.uuid4())
        self.server.run_store.save({
            "id": self.run_id,
            "status": "COMPLETED",
            "targetUrl": "http://127.0.0.1:8080/example",
            "assessmentScope": "whole-site",
            "actions": [],
            "observations": [],
            "warnings": [],
        })

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temporary.cleanup()

    def post_json(self, path, payload):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_review_then_approve_returns_patch_only_for_matching_source(self):
        source = '<label>Email</label><input>\n'
        review = self.post_json(
            f"/api/runs/{self.run_id}/source-review",
            {"sourceContext": {"files": [{"path": "index.html", "content": source}]}},
        )
        self.assertEqual("PATCH_READY", review["sourceReview"]["status"])
        self.assertEqual(
            [{"path": "index.html", "content": '<label for="email">Email</label><input id="email">\n'}],
            self.post_json(
                f"/api/runs/{self.run_id}/source-fix-approve",
                {"sourceContext": {"files": [{"path": "index.html", "content": source}]}},
            )["appliableFiles"],
        )

    def test_approval_rejects_a_changed_source_baseline(self):
        self.post_json(
            f"/api/runs/{self.run_id}/source-review",
            {"sourceContext": {"files": [{"path": "index.html", "content": "original\n"}]}},
        )
        request = Request(
            self.base_url + f"/api/runs/{self.run_id}/source-fix-approve",
            data=json.dumps({"sourceContext": {"files": [{"path": "index.html", "content": "changed\n"}]}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as failure:
            urlopen(request, timeout=3)
        self.assertEqual(409, failure.exception.code)
        self.assertIn("changed since the proposal", failure.exception.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
