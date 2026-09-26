import socket
import unittest
from unittest import mock

from access_trace.browser import _WebPageRequestPolicy
from access_trace.domain import ValidationError, validate_target_url
from access_trace.url_policy import is_public_web_destination


class PublicDestinationTests(unittest.TestCase):
    def test_rejects_private_literal_ip_targets(self):
        for host in ("10.0.0.1", "169.254.169.254", "[fc00::1]", "0.0.0.0"):
            with self.subTest(host=host), self.assertRaises(ValidationError):
                validate_target_url(f"http://{host}/", 8080)

    def test_rejects_loopback_urls_outside_controlled_pages(self):
        for url in (
            "http://localhost:8080/admin",
            "http://127.0.0.1:9999/docs/demos/fixed/index.html",
        ):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                validate_target_url(url, 8080)

    def test_rejects_host_when_any_dns_answer_is_non_public(self):
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]
        with mock.patch("access_trace.url_policy.socket.getaddrinfo", return_value=answers):
            self.assertFalse(is_public_web_destination("https://public.example/resource"))

    def test_rejects_unresolvable_host(self):
        with mock.patch("access_trace.url_policy.socket.getaddrinfo", side_effect=socket.gaierror):
            self.assertFalse(is_public_web_destination("https://missing.example/"))

    def test_accepts_public_dns_answers(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        with mock.patch("access_trace.url_policy.socket.getaddrinfo", return_value=answers):
            self.assertTrue(is_public_web_destination("https://public.example/"))


class WebRequestPolicyTests(unittest.TestCase):
    def setUp(self):
        self.connection = mock.Mock()
        self.policy = _WebPageRequestPolicy(self.connection, "https://example.com/start", "main")

    def _paused(self, url, resource_type="Document", method="GET", frame_id="main"):
        self.policy.handle_event({
            "method": "Fetch.requestPaused",
            "params": {
                "requestId": "request-1",
                "frameId": frame_id,
                "resourceType": resource_type,
                "request": {"url": url, "method": method},
            },
        })

    def test_blocks_redirect_to_private_ip_before_request_continues(self):
        self._paused("http://169.254.169.254/latest/meta-data/")
        self.connection.send_checked_call.assert_called_once_with(
            "Fetch.failRequest", {"requestId": "request-1", "errorReason": "BlockedByClient"}
        )

    def test_blocks_off_origin_document_navigation(self):
        with mock.patch("access_trace.browser.is_public_web_destination", return_value=True):
            self._paused("https://elsewhere.example/")
        self.connection.send_checked_call.assert_called_once_with(
            "Fetch.failRequest", {"requestId": "request-1", "errorReason": "BlockedByClient"}
        )

    def test_allows_public_asset(self):
        with mock.patch("access_trace.browser.is_public_web_destination", return_value=True):
            self._paused("https://cdn.example.net/a.css", resource_type="Stylesheet")
        self.connection.send_checked_call.assert_called_once_with(
            "Fetch.continueRequest", {"requestId": "request-1"}
        )

    def test_blocks_cross_origin_post(self):
        with mock.patch("access_trace.browser.is_public_web_destination", return_value=True):
            self._paused("https://cdn.example.net/collect", resource_type="XHR", method="POST")
        self.connection.send_checked_call.assert_called_once_with(
            "Fetch.failRequest", {"requestId": "request-1", "errorReason": "BlockedByClient"}
        )

    def test_blocks_request_without_resource_type(self):
        with mock.patch("access_trace.browser.is_public_web_destination", return_value=True):
            self._paused("https://example.com/start", resource_type=None)
        self.connection.send_checked_call.assert_called_once_with(
            "Fetch.failRequest", {"requestId": "request-1", "errorReason": "BlockedByClient"}
        )


if __name__ == "__main__":
    unittest.main()
