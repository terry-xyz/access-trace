import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from access_trace.server import create_server


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

    def test_site_file_safety_module_is_served(self):
        for module_path in ("/src/source-context.mjs", "/src/source-apply.mjs"):
            with self.subTest(module_path=module_path):
                with urlopen(self.base_url + module_path, timeout=2) as response:
                    self.assertEqual(200, response.status)
                    self.assertEqual("text/javascript; charset=utf-8", response.headers["Content-Type"])
                    self.assertIn(b"export ", response.read())

    def test_retired_demo_and_sample_routes_are_not_served(self):
        for path in ("/docs/demos/fixed/index.html", "/docs/demos/broken/index.html", "/src/sample-report.mjs", "/src/site-files.mjs"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as failure:
                urlopen(self.base_url + path, timeout=2)
            self.assertEqual(404, failure.exception.code)
            failure.exception.close()

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

if __name__ == "__main__":
    unittest.main()
