"""HTTP boundary for page inputs and first-run assessment evidence."""

import json
import mimetypes
import os
import re
import shutil
import threading
import uuid
from email.parser import BytesParser
from email.policy import default as email_policy
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Dict, Optional
from urllib.parse import quote, unquote, urlsplit

from .domain import CONTROLLED_SCHEME, ValidationError, create_run
from .evidence import REVIEW_UNAVAILABLE_REASON
from .journey import execute_assessment
from .planner import CodexPlanner
from .report import review_evidence
from .source_context import (
    MAX_SOURCE_REQUEST_BYTES,
    SourceContextError,
    prepare_source_context,
)
from .source_review import CodexSourceReviewer, SourceReviewError
from .store import RunStore


MAX_REQUEST_BYTES = 64 * 1024
MAX_LOCAL_SITE_BYTES = 20 * 1024 * 1024
MAX_LOCAL_SITE_REQUEST_BYTES = 22 * 1024 * 1024
MAX_LOCAL_SITE_FILES = 200
MAX_LOCAL_SITE_FILE_BYTES = 5 * 1024 * 1024
RUN_ID_PATTERN = re.compile(r"^[0-9a-f-]+$")
SITE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
LOCAL_SITE_PATH_PATTERN = re.compile(r"^/sites/([0-9a-f]{32})/(.+)$")
STATIC_ROOT = Path(__file__).resolve().parent.parent
STATIC_ASSETS = {
    "/assets/access-trace-logo-dark.svg": (STATIC_ROOT / "assets" / "access-trace-logo-dark.svg", "image/svg+xml"),
    "/src/assessment.mjs": (STATIC_ROOT / "src" / "assessment.mjs", "text/javascript; charset=utf-8"),
    "/src/brand-theme.css": (STATIC_ROOT / "src" / "brand-theme.css", "text/css; charset=utf-8"),
    "/src/comparison.mjs": (STATIC_ROOT / "src" / "comparison.mjs", "text/javascript; charset=utf-8"),
    "/src/live-comparison.mjs": (STATIC_ROOT / "src" / "live-comparison.mjs", "text/javascript; charset=utf-8"),
    "/src/main.mjs": (STATIC_ROOT / "src" / "main.mjs", "text/javascript; charset=utf-8"),
    "/src/styles.css": (STATIC_ROOT / "src" / "styles.css", "text/css; charset=utf-8"),
}


class _HTMLRootDetector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.found_html = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "html":
            self.found_html = True


class LocalHTMLStore:
    """Store uploaded page assets under opaque per-site directories."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.directory.is_symlink():
            raise ValueError("local HTML store must be a dedicated data directory")
        self.directory = self.directory.resolve()

    def save(self, files) -> str:
        site_id = uuid.uuid4().hex
        site_directory = self.directory / site_id
        site_directory.mkdir(mode=0o700)
        try:
            for relative_path, contents in files:
                safe_path = _safe_site_path(relative_path)
                destination = site_directory.joinpath(*PurePosixPath(safe_path).parts)
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(
                    str(destination),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                with os.fdopen(descriptor, "wb") as target:
                    target.write(contents)
        except Exception:
            shutil.rmtree(site_directory, ignore_errors=True)
            raise
        return site_id

    def get(self, site_id: str, relative_path: str) -> Optional[bytes]:
        if not SITE_ID_PATTERN.fullmatch(site_id):
            return None
        try:
            safe_path = _safe_site_path(relative_path)
        except ValidationError:
            return None
        site_directory = self.directory / site_id
        path = site_directory.joinpath(*PurePosixPath(safe_path).parts)
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(site_directory.resolve(strict=True))
            descriptor = os.open(str(resolved), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except (OSError, ValueError):
            return None
        with os.fdopen(descriptor, "rb") as source:
            return source.read(MAX_LOCAL_SITE_FILE_BYTES + 1)


def _safe_site_path(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValidationError("page file has an invalid relative path")
    if "\\" in value or "\x00" in value or value.startswith("/"):
        raise ValidationError("page file paths must be relative")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValidationError("page file paths must not contain dot segments")
    return "/".join(parts)


class AccessTraceServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address,
        handler_class,
        run_directory: Path,
        planner_factory=None,
        source_reviewer_factory=None,
    ):
        self.run_store = RunStore(run_directory)
        self.site_store = LocalHTMLStore(self.run_store.directory / "sites")
        self.planner_factory = planner_factory or CodexPlanner
        self.source_reviewer_factory = source_reviewer_factory or CodexSourceReviewer
        self.active_planners = {}
        self.active_source_reviewers = {}
        self.active_runs = {}
        self.cancelled_run_ids = set()
        self.cancelled_source_review_ids = set()
        self.active_planners_lock = threading.Lock()
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
        if path in {"/", "/index.html"}:
            self.send_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if path == "/health":
            self.send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/api/runs/latest":
            run = self.server.run_store.latest()
            if run is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "No completed run found"}})
                return
            self.send_json(HTTPStatus.OK, run)
            return
        asset = STATIC_ASSETS.get(path)
        if asset is not None:
            self.send_file(asset[0], asset[1])
            return
        if path.startswith("/docs/demos/"):
            self.get_demo_document(path)
            return
        local_site_match = LOCAL_SITE_PATH_PATTERN.fullmatch(path)
        if local_site_match:
            site_id = local_site_match.group(1)
            relative_path = unquote(local_site_match.group(2))
            contents = self.server.site_store.get(site_id, relative_path)
            if contents is None:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Local page file not found"}})
                return
            if Path(relative_path).suffix.lower() in {".html", ".htm"}:
                self.send_local_html(contents)
            else:
                content_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
                self.send_asset(contents, content_type)
            return
        if path.startswith("/api/runs/"):
            self.get_run(path.rsplit("/", 1)[-1])
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not found"}})

    def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        path = urlsplit(self.path).path
        if not self.origin_is_controlled():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": {"message": "Cross-origin requests are not allowed"}})
            return
        if path == "/api/sites":
            self.upload_local_site()
            return
        if path.startswith("/api/runs/") and path.endswith("/execute"):
            self.execute_run(path)
            return
        if path.startswith("/api/runs/") and path.endswith("/source-review"):
            self.review_source_context(path)
            return
        if path.startswith("/api/runs/") and path.endswith("/cancel"):
            self.cancel_run(path)
            return
        if path != "/api/runs":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Not found"}})
            return

        try:
            payload = self.read_json()
            run = create_run(
                payload, self.server.controlled_port, self.server.controlled_scheme
            )
            if run.get("targetVersion") == "local":
                uploaded_site = LOCAL_SITE_PATH_PATTERN.fullmatch(
                    urlsplit(run["targetUrl"]).path
                )
                site_id, entrypoint = uploaded_site.groups()
                if self.server.site_store.get(site_id, unquote(entrypoint)) is None:
                    raise ValidationError("uploaded local page file was not found")
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

    def get_demo_document(self, request_path: str):
        relative_path = unquote(request_path[len("/docs/demos/") :])
        try:
            safe_path = _safe_site_path(relative_path)
            root = (STATIC_ROOT / "docs" / "demos").resolve(strict=True)
            document = root.joinpath(*PurePosixPath(safe_path).parts).resolve(strict=True)
            document.relative_to(root)
            if not document.is_file():
                raise FileNotFoundError
            content_type = mimetypes.guess_type(document.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type in {"application/javascript"}:
                content_type += "; charset=utf-8"
            self.send_file(document, content_type)
        except (ValidationError, OSError, ValueError):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Demo document not found"}})

    def upload_local_site(self):
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "multipart/form-data":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": {"message": "Choose an HTML file or site folder"}})
            return
        try:
            raw_body = self.read_body(MAX_LOCAL_SITE_REQUEST_BYTES)
            envelope = (
                ("Content-Type: " + self.headers.get("Content-Type", "") + "\r\n")
                + "MIME-Version: 1.0\r\n\r\n"
            ).encode("ascii") + raw_body
            message = BytesParser(policy=email_policy).parsebytes(envelope)
            if not message.is_multipart():
                raise ValidationError("page files upload was not a multipart form")
            files = []
            entrypoint = None
            total_bytes = 0
            seen_paths = set()
            for part in message.iter_parts():
                field_name = part.get_param("name", header="content-disposition")
                payload = part.get_payload(decode=True) or b""
                if field_name == "entrypoint":
                    entrypoint = payload.decode("utf-8")
                    continue
                if field_name != "files" or not part.get_filename():
                    continue
                relative_path = _safe_site_path(part.get_filename())
                if relative_path in seen_paths:
                    raise ValidationError("page files contain duplicate relative paths")
                if len(payload) > MAX_LOCAL_SITE_FILE_BYTES:
                    raise ValidationError("each page file must be 5 MiB or smaller")
                seen_paths.add(relative_path)
                total_bytes += len(payload)
                if total_bytes > MAX_LOCAL_SITE_BYTES:
                    raise ValidationError("page files must total 20 MiB or less")
                files.append((relative_path, payload))
                if len(files) > MAX_LOCAL_SITE_FILES:
                    raise ValidationError("choose no more than 200 page files")

            entrypoint = _safe_site_path(entrypoint)
            file_map = dict(files)
            contents = file_map.get(entrypoint)
            if contents is None:
                raise ValidationError("choose an HTML page included with the selected files")
            markup = contents.decode("utf-8")
            if "\x00" in markup:
                raise ValidationError("HTML must be UTF-8 text")
            detector = _HTMLRootDetector()
            detector.feed(markup)
            detector.close()
            if not detector.found_html:
                raise ValidationError("file must contain an HTML document")
            if Path(entrypoint).suffix.lower() not in {".html", ".htm"}:
                raise ValidationError("page entry point must be an HTML file")
            site_id = self.server.site_store.save(files)
        except ValidationError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(error)}})
            return
        except UnicodeDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": "Page files must use UTF-8 text filenames and HTML"}})
            return

        target_url = self.base_url() + "/sites/" + site_id + "/" + quote(entrypoint, safe="/")
        self.send_json(
            HTTPStatus.CREATED,
            {"siteId": site_id, "targetUrl": target_url, "targetVersion": "local", "entrypoint": entrypoint},
        )

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
        planner = None
        registered = False
        try:
            planner = self.server.planner_factory()
            with self.server.active_planners_lock:
                if run_id in self.server.active_planners:
                    self.send_json(
                        HTTPStatus.CONFLICT,
                        {"error": {"message": "Run is already executing"}},
                    )
                    return
                self.server.active_planners[run_id] = planner
                self.server.active_runs[run_id] = run
                registered = True
            completed = execute_assessment(
                run,
                self.server.run_store.directory,
                planner=planner,
                lifecycle_lock=self.server.active_planners_lock,
                cancellation_requested=lambda: (
                    run_id in self.server.cancelled_run_ids
                ),
            )
            with self.server.active_planners_lock:
                # The journey owns its terminal status, including a status
                # produced after a cancellation request races with completion.
                self.server.cancelled_run_ids.discard(run_id)
                self.server.run_store.save(completed)
            try:
                review_planner = self.server.planner_factory()
                review = review_evidence(
                    completed,
                    self.server.run_store.directory,
                    review_planner,
                )
            except Exception:
                completed["evidenceHandoff"]["reporting"] = {
                    "status": "unavailable",
                    "reason": REVIEW_UNAVAILABLE_REASON,
                }
            else:
                completed["evidenceHandoff"]["reporting"] = {
                    "status": "available",
                    **review,
                }
            self.server.run_store.save(completed)
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(error)}})
            return
        finally:
            if registered:
                with self.server.active_planners_lock:
                    if self.server.active_planners.get(run_id) is planner:
                        del self.server.active_planners[run_id]
                    if self.server.active_runs.get(run_id) is run:
                        del self.server.active_runs[run_id]
                    self.server.cancelled_run_ids.discard(run_id)
        self.send_json(HTTPStatus.OK, completed)

    def review_source_context(self, path: str):
        raw_run_id = path[len("/api/runs/") : -len("/source-review")].rstrip("/")
        run_id = unquote(raw_run_id)
        if not RUN_ID_PATTERN.fullmatch(run_id):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Run not found"}})
            return

        run = self.server.run_store.get(run_id)
        if run is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Run not found"}})
            return
        if run.get("status") != "BLOCKED":
            self.send_json(
                HTTPStatus.CONFLICT,
                {"error": {"message": "Source review is available only for blocked runs"}},
            )
            return
        if "sourceReview" in run:
            self.send_json(
                HTTPStatus.CONFLICT,
                {"error": {"message": "Source review has already been requested for this run"}},
            )
            return

        context = None
        reviewer = None
        registered = False
        try:
            try:
                payload = self.read_json(MAX_SOURCE_REQUEST_BYTES)
            except (ValidationError, UnicodeDecodeError, json.JSONDecodeError) as error:
                self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": {"message": "request body must be valid JSON: " + str(error)}},
                )
                return
            if not isinstance(payload, dict) or set(payload) != {"sourceContext"}:
                self.send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": {"message": 'request body must contain only "sourceContext"'}},
                )
                return
            try:
                context = prepare_source_context(payload["sourceContext"])
            except SourceContextError as error:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(error)}})
                return

            skipped = [dict(item) for item in context.skipped]
            if not context.files:
                with self.server.active_planners_lock:
                    current = self.server.run_store.get(run_id)
                    if current is None:
                        status = HTTPStatus.NOT_FOUND
                        response = {"error": {"message": "Run not found"}}
                    elif current.get("status") != "BLOCKED":
                        status = HTTPStatus.CONFLICT
                        response = {
                            "error": {
                                "message": "Source review is available only for blocked runs"
                            }
                        }
                    elif "sourceReview" in current or run_id in self.server.active_source_reviewers:
                        status = HTTPStatus.CONFLICT
                        response = {
                            "error": {
                                "message": "Source review has already been requested for this run"
                            }
                        }
                    else:
                        current["sourceReview"] = {
                            "status": "NO_PATCH",
                            "summary": (
                                "No eligible text files were supplied for review, "
                                "so no patch was generated."
                            ),
                            "relevantPaths": [],
                            "patch": "",
                            "skipped": skipped,
                        }
                        self.server.run_store.save(current)
                        status = HTTPStatus.OK
                        response = current
                self.send_json(status, response)
                return

            try:
                reviewer = self.server.source_reviewer_factory()
            except Exception:
                with self.server.active_planners_lock:
                    current = self.server.run_store.get(run_id)
                    if current is None:
                        status = HTTPStatus.NOT_FOUND
                        response = {"error": {"message": "Run not found"}}
                    elif current.get("status") != "BLOCKED":
                        status = HTTPStatus.CONFLICT
                        response = {
                            "error": {
                                "message": "Source review is available only for blocked runs"
                            }
                        }
                    elif "sourceReview" in current:
                        status = HTTPStatus.CONFLICT
                        response = {
                            "error": {
                                "message": "Source review has already been requested for this run"
                            }
                        }
                    elif run_id in self.server.active_source_reviewers:
                        status = HTTPStatus.CONFLICT
                        response = {
                            "error": {"message": "Source review is already in progress"}
                        }
                    else:
                        current["sourceReview"] = {
                            "status": "FAILED",
                            "summary": "The source reviewer could not be started.",
                            "relevantPaths": [],
                            "patch": "",
                            "skipped": skipped,
                        }
                        self.server.run_store.save(current)
                        status = HTTPStatus.OK
                        response = current
                self.send_json(status, response)
                return

            with self.server.active_planners_lock:
                current = self.server.run_store.get(run_id)
                if current is None:
                    status = HTTPStatus.NOT_FOUND
                    payload = {"error": {"message": "Run not found"}}
                elif current.get("status") != "BLOCKED":
                    status = HTTPStatus.CONFLICT
                    payload = {
                        "error": {"message": "Source review is available only for blocked runs"}
                    }
                elif "sourceReview" in current:
                    status = HTTPStatus.CONFLICT
                    payload = {
                        "error": {
                            "message": "Source review has already been requested for this run"
                        }
                    }
                elif run_id in self.server.active_source_reviewers:
                    status = HTTPStatus.CONFLICT
                    payload = {"error": {"message": "Source review is already in progress"}}
                else:
                    current["sourceReview"] = {
                        "status": "IN_PROGRESS",
                        "summary": "Reviewing uploaded files against browser evidence.",
                        "relevantPaths": [],
                        "patch": "",
                        "skipped": skipped,
                    }
                    self.server.active_source_reviewers[run_id] = reviewer
                    registered = True
                    self.server.run_store.save(current)
                    status = None
                    payload = None
                    run = current

            if status is not None:
                self.send_json(status, payload)
                return

            try:
                review_result = reviewer.review(run, context)
                skipped = [dict(item) for item in context.skipped]
                source_review = {
                    "status": review_result["status"],
                    "summary": review_result["summary"],
                    "relevantPaths": review_result["relevantPaths"],
                    "patch": review_result["patch"],
                    "skipped": skipped,
                }
            except SourceReviewError as error:
                skipped = [dict(item) for item in context.skipped]
                source_review = {
                    "status": "FAILED",
                    "summary": str(error).strip()[:2000] or "Source review failed.",
                    "relevantPaths": [],
                    "patch": "",
                    "skipped": skipped,
                }
            except Exception:
                skipped = [dict(item) for item in context.skipped]
                source_review = {
                    "status": "FAILED",
                    "summary": "The source reviewer failed unexpectedly.",
                    "relevantPaths": [],
                    "patch": "",
                    "skipped": skipped,
                }

            with self.server.active_planners_lock:
                if run_id in self.server.cancelled_source_review_ids:
                    source_review = {
                        "status": "CANCELLED",
                        "summary": "Source review was cancelled.",
                        "relevantPaths": [],
                        "patch": "",
                        "skipped": skipped,
                    }
                completed = self.server.run_store.get(run_id)
                if completed is None:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Run not found"}})
                    return
                completed["sourceReview"] = source_review
                self.server.run_store.save(completed)
            self.send_json(HTTPStatus.OK, completed)
        finally:
            if registered:
                with self.server.active_planners_lock:
                    if self.server.active_source_reviewers.get(run_id) is reviewer:
                        del self.server.active_source_reviewers[run_id]
                    self.server.cancelled_source_review_ids.discard(run_id)
            if context is not None:
                context.cleanup()

    def cancel_run(self, path: str):
        raw_run_id = path[len("/api/runs/") : -len("/cancel")].rstrip("/")
        run_id = unquote(raw_run_id)
        if not RUN_ID_PATTERN.fullmatch(run_id):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"message": "Run not found"}})
            return

        with self.server.active_planners_lock:
            run = self.server.run_store.get(run_id)
            active_run = self.server.active_runs.get(run_id)
            if run is None:
                status = HTTPStatus.NOT_FOUND
                payload = {"error": {"message": "Run not found"}}
            elif (
                isinstance(run.get("sourceReview"), dict)
                and run["sourceReview"].get("status") == "IN_PROGRESS"
            ):
                reviewer = self.server.active_source_reviewers.get(run_id)
                if reviewer is None:
                    status = HTTPStatus.CONFLICT
                    payload = {
                        "error": {"message": "Source review is active, but its reviewer cannot be cancelled"}
                    }
                else:
                    cancel = getattr(reviewer, "cancel", None)
                    if not callable(cancel):
                        status = HTTPStatus.CONFLICT
                        payload = {
                            "error": {"message": "Source review is active, but its reviewer cannot be cancelled"}
                        }
                    else:
                        try:
                            cancel()
                        except Exception:
                            status = HTTPStatus.CONFLICT
                            payload = {
                                "error": {"message": "Source review is active, but could not be cancelled"}
                            }
                        else:
                            self.server.cancelled_source_review_ids.add(run_id)
                            status = HTTPStatus.ACCEPTED
                            payload = {"id": run_id, "status": "CANCELLATION_REQUESTED"}
            elif (active_run if isinstance(active_run, dict) else run).get("status") != "IN_PROGRESS":
                status = HTTPStatus.CONFLICT
                payload = {"error": {"message": "Run is not active or cancellable"}}
            else:
                planner = self.server.active_planners.get(run_id)
                if planner is None:
                    status = HTTPStatus.CONFLICT
                    payload = {"error": {"message": "Run is not active or cancellable"}}
                else:
                    cancel = getattr(planner, "cancel", None)
                    if not callable(cancel):
                        status = HTTPStatus.CONFLICT
                        payload = {
                            "error": {"message": "Run is active, but its planner cannot be cancelled"}
                        }
                    else:
                        try:
                            cancel()
                        except Exception:
                            status = HTTPStatus.CONFLICT
                            payload = {
                                "error": {"message": "Run is active, but its planner could not be cancelled"}
                            }
                        else:
                            self.server.cancelled_run_ids.add(run_id)
                            status = HTTPStatus.ACCEPTED
                            payload = {"id": run_id, "status": "CANCELLATION_REQUESTED"}

        self.send_json(status, payload)

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

    def read_json(self, maximum_bytes: int = MAX_REQUEST_BYTES) -> Dict[str, Any]:
        raw_body = self.read_body(maximum_bytes)
        return json.loads(raw_body.decode("utf-8"))

    def read_body(self, maximum_bytes: int) -> bytes:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            raise ValidationError("request body is required")
        try:
            length = int(content_length)
        except ValueError:
            raise ValidationError("Content-Length must be numeric")
        if length < 0 or length > maximum_bytes:
            raise ValidationError("request body is too large")
        raw_body = self.rfile.read(length)
        if len(raw_body) != length:
            raise ValidationError("request body is incomplete")
        return raw_body

    def origin_is_controlled(self) -> bool:
        """Reject browser-originated writes from uploaded opaque-origin pages.

        Requests without Origin remain available to local command-line clients.
        """
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        try:
            parsed = urlsplit(origin)
            port = parsed.port if parsed.port is not None else 80
        except ValueError:
            return False
        return (
            parsed.scheme == self.server.controlled_scheme
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and port == self.server.controlled_port
            and not parsed.username
            and not parsed.password
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
        )

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

    def send_local_html(self, contents: bytes):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(contents)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline' "
            + self.base_url()
            + "; style-src 'unsafe-inline' "
            + self.base_url()
            + "; img-src data: "
            + self.base_url()
            + "; font-src data: "
            + self.base_url()
            + "; media-src data: "
            + self.base_url()
            + "; connect-src 'none'; "
            "form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(contents)

    def send_asset(self, contents: bytes, content_type: str):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(contents)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(contents)

    def send_file(self, path: Path, content_type: str):
        contents = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(contents)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(contents)

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


def create_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    run_directory: Optional[Path] = None,
    planner_factory=None,
    source_reviewer_factory=None,
):
    directory = Path(run_directory or ".access-trace/runs")
    return AccessTraceServer(
        (host, port),
        AccessTraceHandler,
        directory,
        planner_factory=planner_factory,
        source_reviewer_factory=source_reviewer_factory,
    )
