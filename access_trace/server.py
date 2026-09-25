"""HTTP boundary for the controlled target and first-run evidence."""

import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlsplit

from .demo import demo_page, landing_page
from .domain import CONTROLLED_SCHEME, ValidationError, create_run
from .journey import execute_fixed_goal
from .store import RunStore


MAX_REQUEST_BYTES = 64 * 1024
RUN_ID_PATTERN = re.compile(r"^[0-9a-f-]+$")


class AccessTraceServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_class, run_directory: Path):
        self.run_store = RunStore(run_directory)
        self.controlled_scheme = CONTROLLED_SCHEME
        self.controlled_host = self._public_host(server_address[0])
        super().__init__(server_address, handler_class)
        self.controlled_port = self.server_port
        self.controlled_origin = self._origin()

    def _public_host(self, bound_host: str) -> str:
        normalized = bound_host.strip("[]").lower()
        if normalized in {"", "0.0.0.0"}:
            return "127.0.0.1"
        if normalized == "::":
            return "::1"
        return normalized

    def _origin(self) -> str:
        host = self.controlled_host
        if ":" in host:
            host = "[" + host + "]"
        return "{0}://{1}:{2}".format(self.controlled_scheme, host, self.controlled_port)


class AccessTraceHandler(BaseHTTPRequestHandler):
    server: AccessTraceServer

    def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urlsplit(self.path).path
        if path == "/":
            self.send_html(landing_page(self.base_url()))
            return
        if path == "/health":
            self.send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/demo/fixed":
            self.send_html(demo_page("fixed"))
            return
        if path == "/demo/broken":
            self.send_html(demo_page("broken"))
            return
        if path.startswith("/api/runs/"):
            self.get_run(path.rsplit("/", 1)[-1])
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not found"}})

    def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urlsplit(self.path).path
        if path.startswith("/api/runs/") and path.endswith("/execute"):
            self.execute_run(path)
            return
        if path != "/api/runs":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not found"}})
            return

        try:
            payload = self.read_json()
            run = create_run(
                payload, self.server.controlled_port, self.server.controlled_scheme
            )
            self.server.run_store.save(run)
        except ValidationError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(error)}})
            return
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": {"message": "request body must be valid JSON: " + str(error)}},
            )
            return

        self.send_json(HTTPStatus.CREATED, run)

    def execute_run(self, path: str):
        raw_run_id = path[len("/api/runs/") : -len("/execute")].rstrip("/")
        run_id = unquote(raw_run_id)
        if not RUN_ID_PATTERN.fullmatch(run_id):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Run not found"}})
            return
        run = self.server.run_store.get(run_id)
        if run is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Run not found"}})
            return
        if run.get("status") != "IN_PROGRESS":
            self.send_json(
                HTTPStatus.CONFLICT,
                {"error": {"message": "Run has already reached a terminal state"}},
            )
            return
        try:
            completed = execute_fixed_goal(run, self.server.run_store.directory)
            self.server.run_store.save(completed)
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(error)}})
            return
        self.send_json(HTTPStatus.OK, completed)

    def get_run(self, raw_run_id: str):
        run_id = unquote(raw_run_id)
        if not RUN_ID_PATTERN.fullmatch(run_id):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Run not found"}})
            return
        run = self.server.run_store.get(run_id)
        if run is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Run not found"}})
            return
        self.send_json(HTTPStatus.OK, run)

    def read_json(self) -> Dict[str, Any]:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            raise ValidationError("request body is required")
        try:
            length = int(content_length)
        except ValueError:
            raise ValidationError("Content-Length must be numeric")
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValidationError("request body is too large")
        raw_body = self.rfile.read(length)
        if len(raw_body) != length:
            raise ValidationError("request body is incomplete")
        return json.loads(raw_body.decode("utf-8"))

    def base_url(self) -> str:
        return self.server.controlled_origin

    def send_html(self, body: str):
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, status: HTTPStatus, payload: Dict[str, Any]):
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format_string: str, *args: Any):
        return


def create_server(host: str = "127.0.0.1", port: int = 8080, run_directory: Optional[Path] = None):
    directory = Path(run_directory or ".access-trace/runs")
    return AccessTraceServer((host, port), AccessTraceHandler, directory)
