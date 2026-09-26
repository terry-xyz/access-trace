import http.client
import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from access_trace.server import create_server
from access_trace.source_context import prepare_source_context


class ServerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, Path(self.temporary.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temporary.cleanup()

    def test_untrusted_host_cannot_read_or_write_api(self):
        for method, path, body in (
            ("GET", "/api/runs/latest", None),
            ("POST", "/api/runs", b"{}"),
        ):
            request = Request(
                self.base_url + path,
                data=body,
                headers={"Host": "attacker.example", "Content-Type": "application/json"},
                method=method,
            )
            with self.subTest(method=method), self.assertRaises(HTTPError) as failure:
                urlopen(request, timeout=2)
            self.assertEqual(421, failure.exception.code)
            failure.exception.close()

    def test_uploaded_svg_gets_document_sandbox(self):
        site_id = self.server.site_store.save(
            [("index.html", b"<html></html>"), ("image.svg", b"<svg></svg>")]
        )
        with urlopen(self.base_url + f"/sites/{site_id}/image.svg", timeout=2) as response:
            self.assertEqual(200, response.status)
            self.assertIn("sandbox", response.headers["Content-Security-Policy"])
            self.assertNotIn("allow-same-origin", response.headers["Content-Security-Policy"])

    def test_source_context_module_is_served(self):
        for module_path in ("/src/source-context.mjs", "/src/source-apply.mjs"):
            with self.subTest(module_path=module_path):
                with urlopen(self.base_url + module_path, timeout=2) as response:
                    self.assertEqual(200, response.status)
                    self.assertEqual("text/javascript; charset=utf-8", response.headers["Content-Type"])
                    self.assertIn(b"export ", response.read())

    def test_oversized_upload_returns_bad_request(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            connection.request(
                "POST",
                "/api/sites",
                body=b"x",
                headers={
                    "Content-Type": "multipart/form-data; boundary=abc",
                    "Content-Length": str(22 * 1024 * 1024 + 1),
                },
            )
            response = connection.getresponse()
            self.assertEqual(400, response.status)
            self.assertIn("request body is too large", response.read().decode("utf-8"))
        finally:
            connection.close()

    def test_transfer_encoding_with_content_length_is_rejected(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            connection.putrequest("POST", "/api/runs")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Transfer-Encoding", "chunked")
            connection.putheader("Content-Length", "2")
            connection.endheaders(b"{}")
            response = connection.getresponse()
            self.assertEqual(400, response.status)
            self.assertIn("Unsupported request framing", response.read().decode("utf-8"))
        finally:
            connection.close()

    def test_site_upload_rejects_sensitive_files(self):
        boundary = "test-boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"entrypoint\"\r\n\r\nindex.html\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"index.html\"\r\n\r\n<html></html>\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"config/.env\"\r\n\r\nSECRET=1\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        request = Request(
            self.base_url + "/api/sites",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as failure:
            urlopen(request, timeout=2)
        self.assertEqual(400, failure.exception.code)
        self.assertIn("sensitive", failure.exception.read().decode("utf-8"))
        failure.exception.close()

    def _approval_request(self, content, path="src/app.css", patch=None):
        source = "body { color: red; }\n"
        patch = patch or (
            "diff --git a/src/app.css b/src/app.css\n"
            "--- a/src/app.css\n+++ b/src/app.css\n"
            "@@ -1 +1 @@\n-body { color: red; }\n+body { color: blue; }\n"
        )
        run_id = "a" * 32
        run = {
            "id": run_id,
            "status": "COMPLETED",
            "targetUrl": "https://example.test/",
            "sourceReview": {
                "status": "PATCH_READY",
                "patch": patch,
                "proposalDigest": hashlib.sha256(patch.encode()).hexdigest(),
                "relevantPaths": [path],
                "sourceDigests": {path: hashlib.sha256(source.encode()).hexdigest()},
            },
        }
        self.server.run_store.save(run)
        payload = json.dumps({"sourceContext": {"files": [
            {"path": path, "content": content, "selectionType": "file"}
        ]}}).encode()
        request = Request(
            self.base_url + f"/api/runs/{run_id}/source-fix-approve",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def test_approval_returns_exact_replacements_without_server_writes(self):
        status, result = self._approval_request("body { color: red; }\n")
        self.assertEqual(200, status)
        self.assertEqual(
            [{"path": "src/app.css", "content": "body { color: blue; }\n"}],
            result["appliableFiles"],
        )
        self.assertFalse((Path(self.temporary.name) / "src").exists())

    def test_approval_rejects_stale_baseline(self):
        status, result = self._approval_request("body { color: green; }\n")
        self.assertEqual(409, status)
        self.assertIn("changed", result["error"]["message"])

    def test_approval_rejects_wrong_path_and_traversal_patch(self):
        other_path_patch = (
            "diff --git a/src/other.css b/src/other.css\n"
            "--- a/src/other.css\n+++ b/src/other.css\n"
            "@@ -1 +1 @@\n-body { color: red; }\n+body { color: blue; }\n"
        )
        status, _ = self._approval_request("body { color: red; }\n", patch=other_path_patch)
        self.assertEqual(409, status)
        malicious = other_path_patch.replace("src/other.css", "../../outside.css")
        status, _ = self._approval_request("body { color: red; }\n", patch=malicious)
        self.assertEqual(409, status)

    def _post_run_json(self, run_id, endpoint, source_context):
        request = Request(
            self.base_url + f"/api/runs/{run_id}/{endpoint}",
            data=json.dumps({"sourceContext": source_context}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def test_terminal_source_review_proposal_can_be_approved(self):
        source = "body { color: red; }\n"
        patch = (
            "diff --git a/src/app.css b/src/app.css\n"
            "--- a/src/app.css\n+++ b/src/app.css\n"
            "@@ -1 +1 @@\n-body { color: red; }\n+body { color: blue; }\n"
        )

        class FakeReviewer:
            def review(self, run, context):
                self.run_status = run["status"]
                self.reviewed_paths = [item.path for item in context.files]
                return {
                    "status": "PATCH_READY",
                    "summary": "The selector uses the inaccessible color value.",
                    "rootCause": "The body text color lacks sufficient contrast.",
                    "proposedFix": "Use the blue token with stronger contrast.",
                    "relevantPaths": ["src/app.css"],
                    "patch": patch,
                }

        reviewer = FakeReviewer()
        self.server.source_reviewer_factory = lambda: reviewer
        run_id = "c" * 32
        self.server.run_store.save({
            "id": run_id,
            "status": "COMPLETED",
            "targetUrl": "https://example.test/",
            "targetVersion": "web",
            "observations": [],
            "actions": [],
        })
        source_context = {"files": [{
            "path": "src/app.css",
            "content": source,
            "selectionType": "file",
        }]}

        review_status, review_response = self._post_run_json(
            run_id, "source-review", source_context
        )
        self.assertEqual(200, review_status)
        review = review_response["sourceReview"]
        self.assertEqual("PATCH_READY", review["status"])
        self.assertEqual("The body text color lacks sufficient contrast.", review["rootCause"])
        self.assertEqual("Use the blue token with stronger contrast.", review["proposedFix"])
        self.assertEqual("COMPLETED", reviewer.run_status)
        self.assertEqual(["src/app.css"], reviewer.reviewed_paths)

        approval_status, approval_response = self._post_run_json(
            run_id, "source-fix-approve", source_context
        )
        self.assertEqual(200, approval_status)
        self.assertEqual([{
            "path": "src/app.css",
            "content": "body { color: blue; }\n",
        }], approval_response["appliableFiles"])

    def test_source_review_returns_no_patch_and_rejects_nonterminal_run(self):
        class NoPatchReviewer:
            def review(self, run, context):
                return {
                    "status": "NO_PATCH",
                    "summary": "The supplied source does not support a correction.",
                    "rootCause": "",
                    "proposedFix": "",
                    "relevantPaths": [],
                    "patch": "",
                }

        self.server.source_reviewer_factory = NoPatchReviewer
        run_id = "d" * 32
        self.server.run_store.save({
            "id": run_id,
            "status": "INCONCLUSIVE",
            "targetUrl": "https://example.test/",
            "targetVersion": "web",
            "observations": [],
            "actions": [],
        })
        source_context = {"files": [{
            "path": "src/app.css",
            "content": "body {}\n",
            "selectionType": "file",
        }]}
        status, response = self._post_run_json(run_id, "source-review", source_context)
        self.assertEqual(200, status)
        self.assertEqual("NO_PATCH", response["sourceReview"]["status"])

        running_id = "e" * 32
        self.server.run_store.save({
            "id": running_id,
            "status": "IN_PROGRESS",
            "targetUrl": "https://example.test/",
            "targetVersion": "web",
            "observations": [],
            "actions": [],
        })
        status, response = self._post_run_json(running_id, "source-review", source_context)
        self.assertEqual(409, status)
        self.assertIn("terminal", response["error"]["message"])


class SourceContextSecurityTests(unittest.TestCase):
    def test_sensitive_files_are_skipped_even_when_selected_individually(self):
        paths = [
            ".env", "config/.env.production", "certs/private.key",
            "secrets/id_rsa", "config/credentials.json", "config/service-account.json",
            "config/access-token.json", "src/app.py", "tests/test_credentials.py",
        ]
        prepared = prepare_source_context(
            {"files": [{"path": path, "content": "secret", "selectionType": "file"} for path in paths]}
        )
        self.assertEqual(["src/app.py", "tests/test_credentials.py"], [item.path for item in prepared.files])
        self.assertEqual(
            set(paths[:-2]),
            {item["path"] for item in prepared.skipped if item["reason"] == "sensitive-file"},
        )


if __name__ == "__main__":
    unittest.main()
