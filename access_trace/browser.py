"""Private real-browser boundary for bounded keyboard journeys.

The journey code never receives a browser handle, selector, script, or page
source.  This adapter exposes only keyboard input and a deliberately bounded
observation of the current page.
"""

import base64
import binascii
from collections import deque
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit


class BrowserError(RuntimeError):
    """Raised when the isolated browser cannot be used reliably."""


class BrowserActionError(BrowserError):
    """Raised when a permitted keyboard action cannot be delivered."""


class BrowserCleanupError(BrowserError):
    """Raised when the isolated browser or profile cannot be fully removed."""


PERMITTED_KEYS = {
    "Tab",
    "Shift+Tab",
    "Enter",
    "Space",
    "ArrowLeft",
    "ArrowRight",
    "ArrowUp",
    "ArrowDown",
    "Escape",
}
MAX_TYPED_CHARACTERS = 80
MAX_PLANNER_SCREENSHOT_BYTES = 256 * 1024
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
OBSERVATION_SCRIPT = r"""
(() => {
  const compact = (value) => String(value || "").trim().replace(/\s+/g, " ").slice(0, 80);
  const visible = (node) => {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    return !node.hidden && style.display !== "none" && style.visibility !== "hidden";
  };
  const labelFor = (node) => {
    if (!node) return null;
    const aria = node.getAttribute("aria-label");
    if (aria) return compact(aria);
    if (node.id) {
      for (const label of document.querySelectorAll("label")) {
        if (label.htmlFor === node.id) return compact(label.textContent);
      }
    }
    if (node.tagName === "BUTTON") return compact(node.textContent);
    return null;
  };
  const roleFor = (node) => {
    if (!node) return "document";
    const explicit = node.getAttribute("role");
    if (explicit) return compact(explicit);
    if (node.tagName === "BUTTON") return "button";
    if (node.tagName === "TEXTAREA") return "textbox";
    if (node.tagName === "INPUT") {
      return node.type === "checkbox" ? "checkbox" : "textbox";
    }
    if (node.tagName === "A") return "link";
    return node === document.body ? "document" : "generic";
  };
  const control = (node) => {
    if (!node || node === document.body || node === document.documentElement) return {
      role: "document",
      accessibleName: "Fictional contact form",
      tag: "body",
      stableId: "document",
      isStable: true
    };
    const editable = node.tagName === "INPUT" || node.tagName === "TEXTAREA";
    const item = {
      role: roleFor(node),
      accessibleName: labelFor(node),
      tag: node.tagName.toLowerCase(),
      stableId: compact(node.id) || "anonymous-control",
      isStable: Boolean(node.id),
      focusable: true,
    };
    if (editable) {
      item.characterCount = String(node.value || "").length;
      item.acceptedInput = item.characterCount > 0;
      item.validationState = node.validity
        ? (node.validity.valid ? "valid" : "invalid")
        : "not-observed";
    }
    return item;
  };
  const keyboardFocusable = (node) => {
    if (!visible(node) || node.disabled || node.type === "hidden") return false;
    if (node.tagName === "A" && !node.hasAttribute("href")) return false;
    return node.tabIndex >= 0;
  };
  const allControls = Array.from(document.querySelectorAll(
    'a[href], button, input, textarea, select, '
    + '[tabindex]:not([tabindex="-1"])'
  )).filter(keyboardFocusable);
  const controls = allControls.slice(0, 8).map(control);
  const active = document.activeElement || document.body;
  const statuses = Array.from(document.querySelectorAll('[role="status"]'));
  const dialogOpen = Array.from(document.querySelectorAll(
    'dialog[open], [role="dialog"], [aria-modal="true"], [data-overlay], '
    + '[data-modal], .overlay, .modal, [class*="overlay"], [class*="modal"]'
  )).some(visible);
  const successMatched = statuses.some(
    (node) => visible(node) && compact(node.textContent) === "Message sent"
  );
  return {
    url: String(window.location.href).slice(0, 256),
    title: compact(document.title),
    focus: control(active),
    controls,
    controlsTruncated: allControls.length > controls.length,
    successMatched,
    lifecycle: {
      dialogOpen,
    },
  };
})()
"""

EDITABLE_BOUNDS_SCRIPT = r"""
(() => Array.from(document.querySelectorAll("input, textarea")).map((node) => {
  const rect = node.getBoundingClientRect();
  return {left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom};
}))()
"""


def _read_exact(source: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining:
        try:
            chunk = source.recv(remaining)
        except socket.timeout as error:
            raise BrowserError("browser connection timed out") from error
        if not chunk:
            raise BrowserError("browser connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def _redact_png(png: bytes, bounds) -> bytes:
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise BrowserError("browser screenshot was not a PNG")
    position = 8
    image_data = []
    width = height = bit_depth = color_type = None
    while position < len(png):
        length = struct.unpack("!I", png[position : position + 4])[0]
        chunk_type = png[position + 4 : position + 8]
        chunk_data = png[position + 8 : position + 8 + length]
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack("!IIBB", chunk_data[:10])
        elif chunk_type == b"IDAT":
            image_data.append(chunk_data)
        position += 12 + length
        if chunk_type == b"IEND":
            break
    if (width, height, bit_depth, color_type) == (None, None, None, None):
        raise BrowserError("browser screenshot had no image header")
    if bit_depth != 8 or color_type not in {2, 6}:
        raise BrowserError("browser screenshot format cannot be redacted safely")
    channels = 4 if color_type == 6 else 3
    row_size = width * channels
    decoded = zlib.decompress(b"".join(image_data))
    expected_size = height * (row_size + 1)
    if len(decoded) != expected_size:
        raise BrowserError("browser screenshot had unexpected image data")

    rows = []
    offset = 0
    previous = bytearray(row_size)
    for _ in range(height):
        filter_type = decoded[offset]
        filtered = decoded[offset + 1 : offset + 1 + row_size]
        offset += row_size + 1
        row = bytearray(row_size)
        for index, value in enumerate(filtered):
            left = row[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                row[index] = value
            elif filter_type == 1:
                row[index] = (value + left) & 0xFF
            elif filter_type == 2:
                row[index] = (value + above) & 0xFF
            elif filter_type == 3:
                row[index] = (value + ((left + above) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (value + _paeth(left, above, upper_left)) & 0xFF
            else:
                raise BrowserError("browser screenshot used an unsupported filter")
        rows.append(row)
        previous = row

    for bound in bounds:
        left = max(0, int(bound.get("left", 0)) - 4)
        top = max(0, int(bound.get("top", 0)) - 4)
        right = min(width, int(bound.get("right", 0)) + 4)
        bottom = min(height, int(bound.get("bottom", 0)) + 4)
        for y in range(top, bottom):
            row = rows[y]
            for x in range(left, right):
                pixel = x * channels
                row[pixel : pixel + 3] = b"\x20\x20\x20"
                if channels == 4:
                    row[pixel + 3] = 0xFF

    encoded = bytearray()
    for row in rows:
        encoded.append(0)
        encoded.extend(row)
    compressed = zlib.compress(bytes(encoded))

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + chunk_type
            + data
            + struct.pack("!I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    header = struct.pack("!IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


class _WebSocket:
    def __init__(self, url: str, timeout: float = 3.0):
        parsed = urlsplit(url)
        if parsed.scheme != "ws" or not parsed.hostname or not parsed.port:
            raise BrowserError("browser returned an invalid debugging endpoint")
        self.socket = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
        self.socket.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        request = (
            "GET {0} HTTP/1.1\r\n"
            "Host: {1}:{2}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {3}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).format(path, parsed.hostname, parsed.port, key)
        self.socket.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.socket.recv(4096)
        if not response.startswith(b"HTTP/1.1 101"):
            self.close()
            raise BrowserError("browser debugging endpoint refused the connection")
        self._next_call_id = 1
        self._events = deque(maxlen=256)
        self.events_overflowed = False

    def _remember_event(self, message: Dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            return
        if method == "Target.targetCreated":
            info = params.get("targetInfo")
            if not isinstance(info, dict):
                return
            target_info = {
                key: info.get(key)
                for key in ("targetId", "type", "openerId")
                if isinstance(info.get(key), str)
            }
            self._append_event({"method": method, "params": {"targetInfo": target_info}})
        elif method in {"Target.targetDestroyed", "Target.targetCrashed"}:
            target_id = params.get("targetId")
            self._append_event(
                {"method": method, "params": {"targetId": target_id}}
            )
        elif method in {
            "Inspector.targetCrashed",
            "Page.javascriptDialogOpening",
            "Page.javascriptDialogClosed",
            "Page.windowOpen",
        }:
            # Deliberately omit dialog messages and popup URLs from retained CDP
            # event data; their contents are untrusted page data.
            self._append_event({"method": method, "params": {}})
        elif method == "Page.frameNavigated":
            frame = params.get("frame")
            if isinstance(frame, dict) and not frame.get("parentId"):
                url = frame.get("url")
                if isinstance(url, str):
                    self._append_event(
                        {
                            "method": method,
                            "params": {
                                "frameId": frame.get("id"),
                                "url": url[:4096],
                            },
                        }
                    )
        elif method in {"Network.requestWillBeSent", "Page.navigatedWithinDocument"}:
            frame_id = params.get("frameId")
            if isinstance(frame_id, str):
                request = params.get("request")
                url = request.get("url") if isinstance(request, dict) else params.get("url")
                if isinstance(url, str) and (
                    method != "Network.requestWillBeSent"
                    or params.get("type") == "Document"
                ):
                    self._append_event(
                        {
                            "method": method,
                            "params": {"frameId": frame_id, "url": url[:4096]},
                        }
                    )

    def _append_event(self, event: Dict[str, Any]) -> None:
        if len(self._events) == self._events.maxlen:
            self.events_overflowed = True
        self._events.append(event)

    def drain_events(self) -> list:
        events = list(self._events)
        self._events.clear()
        return events

    def send(self, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._send_frame(0x1, encoded)

    def _send_frame(self, opcode: int, data: bytes) -> None:
        mask = os.urandom(4)
        length = len(data)
        if length < 126:
            header = bytes([0x80 | opcode, 0x80 | length])
        elif length < 65536:
            header = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack("!H", length)
        else:
            header = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack("!Q", length)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
        self.socket.sendall(header + mask + masked)

    def receive(self) -> Dict[str, Any]:
        while True:
            first, second = _read_exact(self.socket, 2)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", _read_exact(self.socket, 2))[0]
            elif length == 127:
                length = struct.unpack("!Q", _read_exact(self.socket, 8))[0]
            mask = _read_exact(self.socket, 4) if second & 0x80 else None
            data = _read_exact(self.socket, length)
            if mask:
                data = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
            if opcode == 0x9:
                self._send_control(0xA, data)
                continue
            if opcode == 0x8:
                raise BrowserError("browser debugging endpoint closed the connection")
            if opcode != 0x1:
                continue
            return json.loads(data.decode("utf-8"))

    def _send_control(self, opcode: int, data: bytes) -> None:
        self._send_frame(opcode, data)

    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        call_id = self._next_call_id
        self._next_call_id += 1
        self.send({"id": call_id, "method": method, "params": params or {}})
        while True:
            message = self.receive()
            if isinstance(message.get("method"), str):
                self._remember_event(message)
                continue
            if message.get("id") != call_id:
                continue
            if "error" in message:
                raise BrowserError("browser rejected the requested operation")
            return message.get("result")

    def send_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> int:
        call_id = self._next_call_id
        self._next_call_id += 1
        self.send({"id": call_id, "method": method, "params": params or {}})
        return call_id

    def wait_for_calls(self, call_ids) -> None:
        pending = set(call_ids)
        while pending:
            message = self.receive()
            if isinstance(message.get("method"), str):
                self._remember_event(message)
                continue
            message_id = message.get("id")
            if message_id not in pending:
                continue
            if "error" in message:
                raise BrowserError("browser rejected the requested operation")
            pending.remove(message_id)

    def close(self) -> None:
        try:
            self.socket.close()
        except OSError:
            pass


def _find_chrome() -> Optional[str]:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    return next(
        (candidate for candidate in candidates if candidate and Path(candidate).is_file()),
        None,
    )


def _descendant_process_ids(root_pid: int):
    try:
        output = subprocess.check_output(
            ["ps", "-axo", "pid=,ppid="], text=True, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    children = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            pid, parent_pid = int(fields[0]), int(fields[1])
        except ValueError:
            continue
        children.setdefault(parent_pid, set()).add(pid)
    descendants = set()
    pending = [root_pid]
    while pending:
        parent_pid = pending.pop()
        for child_pid in children.get(parent_pid, set()):
            if child_pid not in descendants:
                descendants.add(child_pid)
                pending.append(child_pid)
    return descendants


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class IsolatedKeyboardBrowser:
    """A fresh, keyboard-only Chrome session with bounded observations."""

    def __init__(self, target_url: str):
        chrome = _find_chrome()
        if chrome is None:
            raise BrowserError("Chrome is not available for a real browser run")
        self.profile_directory = Path(tempfile.mkdtemp(prefix="access-trace-browser-"))
        self.process: Optional[subprocess.Popen] = None
        self.connection: Optional[_WebSocket] = None
        self.browser_connection: Optional[_WebSocket] = None
        self.target_url = target_url
        self.target_id: Optional[str] = None
        self._page_monitor_active = False
        self._main_frame_id: Optional[str] = None
        self._page_open: Optional[bool] = None
        self._popup_observed: Optional[bool] = None
        self._popup_attempted: Optional[bool] = None
        self._crashed: Optional[bool] = None
        self._native_dialog_open: Optional[bool] = None
        self._dialog_observed: Optional[bool] = None
        self._off_loopback_redirect_observed: Optional[bool] = None
        self._navigation_redirect_observed: Optional[bool] = None
        self._main_frame_url: Optional[str] = None
        self._navigation_started = False
        self.debug_port = self._free_port()
        try:
            self.process = subprocess.Popen(
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--remote-allow-origins=*",
                    "--remote-debugging-address=127.0.0.1",
                    "--remote-debugging-port={0}".format(self.debug_port),
                    "--user-data-dir={0}".format(self.profile_directory),
                    "--force-device-scale-factor=1",
                    "--window-size=1280,900",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            browser_websocket_url = self._wait_for_browser()
            self.browser_connection = _WebSocket(browser_websocket_url)
            self.browser_connection.call(
                "Target.setDiscoverTargets", {"discover": True}
            )
            target_id, websocket_url = self._wait_for_page()
            self.target_id = target_id
            self.connection = _WebSocket(websocket_url)
            self.connection.call("Page.enable")
            self.connection.call("Runtime.enable")
            self.connection.call("Inspector.enable")
            frame_tree = self.connection.call("Page.getFrameTree")
            tree = frame_tree.get("frameTree") if isinstance(frame_tree, dict) else None
            main_frame = tree.get("frame") if isinstance(tree, dict) else None
            self._main_frame_id = (
                main_frame.get("id") if isinstance(main_frame, dict) else None
            )
            self.connection.call("Network.enable")
            self._page_monitor_active = True
            self._popup_attempted = False
            self._native_dialog_open = False
            self._crashed = False
            self._refresh_target_state()
            self._navigation_started = True
            self.connection.call("Page.navigate", {"url": target_url})
            self._wait_for_target()
        except Exception as error:
            try:
                self.close()
            except BrowserCleanupError as cleanup_error:
                raise BrowserCleanupError(
                    "isolated browser startup cleanup could not be verified"
                ) from cleanup_error
            raise BrowserError("unable to start the isolated browser") from error

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as source:
            source.bind(("127.0.0.1", 0))
            return int(source.getsockname()[1])

    def _wait_for_browser(self) -> str:
        deadline = time.monotonic() + 5
        endpoint = "http://127.0.0.1:{0}/json/version".format(self.debug_port)
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise BrowserError("isolated browser exited before it was ready")
            try:
                with urllib.request.urlopen(endpoint, timeout=0.5) as response:
                    version = json.loads(response.read().decode("utf-8"))
                websocket_url = version.get("webSocketDebuggerUrl")
                if isinstance(websocket_url, str):
                    return websocket_url
            except (OSError, ValueError):
                pass
            time.sleep(0.05)
        raise BrowserError("isolated browser debugging endpoint did not become ready")

    def _wait_for_page(self) -> tuple:
        deadline = time.monotonic() + 5
        endpoint = "http://127.0.0.1:{0}/json/list".format(self.debug_port)
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise BrowserError("isolated browser exited before it was ready")
            try:
                with urllib.request.urlopen(endpoint, timeout=0.5) as response:
                    pages = json.loads(response.read().decode("utf-8"))
                for page in pages:
                    if (
                        page.get("type") == "page"
                        and isinstance(page.get("id"), str)
                        and page.get("webSocketDebuggerUrl")
                    ):
                        return page["id"], page["webSocketDebuggerUrl"]
            except (OSError, ValueError):
                pass
            time.sleep(0.05)
        raise BrowserError("isolated browser did not become ready")

    def _wait_for_settled_input(self) -> None:
        time.sleep(0.05)

    def _wait_for_target(self) -> None:
        if self.connection is None:
            raise BrowserError("browser is not connected")
        expected_url = self.target_url.rstrip("/")
        deadline = time.monotonic() + 5
        previous_url = None
        stable_observations = 0
        while time.monotonic() < deadline:
            try:
                result = self.connection.call(
                    "Runtime.evaluate",
                    {"expression": "String(window.location.href)", "returnByValue": True},
                )
            except BrowserError:
                self._refresh_target_state()
                if self._page_open is False or self._crashed is True:
                    return
                time.sleep(0.05)
                continue
            current_url = (
                result.get("result", {}).get("value") if isinstance(result, dict) else None
            )
            self._collect_page_events()
            if isinstance(current_url, str) and current_url.rstrip("/") == expected_url:
                self._wait_for_settled_input()
                return
            if isinstance(current_url, str) and current_url not in {"", "about:blank"}:
                stable_observations = (
                    stable_observations + 1 if current_url == previous_url else 1
                )
                if stable_observations >= 2:
                    self._wait_for_settled_input()
                    return
            previous_url = current_url
            time.sleep(0.05)
        self._refresh_target_state()
        if self._page_open is False or self._crashed is True:
            return
        raise BrowserError("isolated browser did not settle on a page")

    def _collect_page_events(self) -> None:
        if self.connection is None:
            return
        events = self.connection.drain_events()
        main_frame_ids = {self._main_frame_id}
        for event in events:
            params = event.get("params")
            frame_id = params.get("frameId") if isinstance(params, dict) else None
            if event.get("method") == "Page.frameNavigated" and isinstance(
                frame_id, str
            ):
                main_frame_ids.add(frame_id)
        for event in events:
            method = event.get("method")
            params = event.get("params", {})
            if method == "Inspector.targetCrashed":
                self._crashed = True
            elif method == "Page.javascriptDialogOpening":
                self._native_dialog_open = True
                self._dialog_observed = True
                self._crashed = False
            elif method == "Page.javascriptDialogClosed":
                self._native_dialog_open = False
            elif method == "Page.windowOpen":
                self._popup_attempted = True
            elif method in {
                "Page.frameNavigated",
                "Page.navigatedWithinDocument",
                "Network.requestWillBeSent",
            }:
                url = params.get("url") if isinstance(params, dict) else None
                frame_id = params.get("frameId") if isinstance(params, dict) else None
                if (
                    method == "Page.frameNavigated"
                    and isinstance(frame_id, str)
                ):
                    self._main_frame_id = frame_id
                if (
                    isinstance(url, str)
                    and isinstance(frame_id, str)
                    and frame_id in main_frame_ids
                ):
                    self._record_main_frame_url(url)

        if self.connection.events_overflowed:
            self._native_dialog_open = None
            if self._dialog_observed is not True:
                self._dialog_observed = None
            if self._popup_attempted is not True:
                self._popup_attempted = None
            if self._off_loopback_redirect_observed is not True:
                self._off_loopback_redirect_observed = None
            if self._navigation_redirect_observed is not True:
                self._navigation_redirect_observed = None
            if self._crashed is not True:
                self._crashed = None

    def _record_main_frame_url(self, url: str) -> None:
        self._main_frame_url = url[:4096]
        if not self._navigation_started or url == "about:blank":
            return
        if self._off_loopback_redirect(url) is True:
            self._off_loopback_redirect_observed = True
        elif not self._same_target_route(url):
            self._navigation_redirect_observed = True

    def _same_target_route(self, url: str) -> bool:
        try:
            observed = urlsplit(url[:4096])
            target = urlsplit(self.target_url)
            observed_port = observed.port or (80 if observed.scheme == "http" else 443)
            target_port = target.port or (80 if target.scheme == "http" else 443)
        except ValueError:
            return False
        return (
            observed.scheme == target.scheme
            and observed.hostname in {"localhost", "127.0.0.1", "::1"}
            and target.hostname in {"localhost", "127.0.0.1", "::1"}
            and observed_port == target_port
            and (observed.path.rstrip("/") or "/")
            == (target.path.rstrip("/") or "/")
            and not observed.query
            and not observed.fragment
        )

    def _collect_target_events(self) -> None:
        if self.browser_connection is None:
            return
        for event in self.browser_connection.drain_events():
            method = event.get("method")
            params = event.get("params", {})
            if method == "Target.targetCreated":
                target_info = params.get("targetInfo", {})
                if (
                    isinstance(target_info, dict)
                    and target_info.get("type") == "page"
                    and target_info.get("targetId") != self.target_id
                ):
                    self._popup_observed = True
            elif method == "Target.targetDestroyed":
                if (
                    isinstance(params, dict)
                    and params.get("targetId") == self.target_id
                ):
                    self._page_open = False
            elif method == "Target.targetCrashed":
                if (
                    isinstance(params, dict)
                    and params.get("targetId") == self.target_id
                ):
                    self._crashed = True

    def _refresh_target_state(self) -> None:
        if self.browser_connection is None or self.target_id is None:
            self._page_open = None
            self._popup_observed = None
            if self._crashed is not True:
                self._crashed = None
            return
        try:
            result = self.browser_connection.call("Target.getTargets")
        except BrowserError:
            if self.process is not None and self.process.poll() is not None:
                self._page_open = False
                if self._crashed is not True:
                    self._crashed = None
            else:
                self._page_open = None
                if self._popup_observed is not True:
                    self._popup_observed = None
                if self._crashed is not True:
                    self._crashed = None
            self._collect_target_events()
            return

        infos = result.get("targetInfos") if isinstance(result, dict) else None
        if not isinstance(infos, list):
            self._page_open = None
            if self._popup_observed is not True:
                self._popup_observed = None
            if self._crashed is not True:
                self._crashed = None
            self._collect_target_events()
            return

        page_infos = [
            info
            for info in infos
            if isinstance(info, dict) and info.get("type") == "page"
        ]
        self._page_open = any(info.get("targetId") == self.target_id for info in page_infos)
        if any(info.get("targetId") != self.target_id for info in page_infos):
            self._popup_observed = True
        elif self._popup_observed is not True:
            self._popup_observed = False
        if (
            self._page_open
            and self._crashed is not True
            and self._page_monitor_active
            and self.connection is not None
            and not self.connection.events_overflowed
        ):
            self._crashed = False
        self._collect_target_events()
        if self.browser_connection.events_overflowed:
            if self._popup_observed is not True:
                self._popup_observed = None
            if self._crashed is not True:
                self._crashed = None

    def _off_loopback_redirect(self, url: Any) -> Optional[bool]:
        if not isinstance(url, str):
            return None
        try:
            observed = urlsplit(url[:4096])
        except ValueError:
            return None
        if observed.hostname is None:
            return None
        return not (
            observed.scheme in {"http", "https"}
            and observed.hostname in LOOPBACK_HOSTS
        )

    def _lifecycle(self, url: Any = None, dialog_open: Optional[bool] = None) -> Dict[str, Any]:
        if self._native_dialog_open is True or dialog_open is True:
            observed_dialog = True
        elif dialog_open is False and self._native_dialog_open is False:
            observed_dialog = False
        else:
            observed_dialog = None
        page_events_overflowed = (
            self.connection is not None and self.connection.events_overflowed
        )
        dialog_observed = self._dialog_observed
        if (
            dialog_observed is None
            and self._page_monitor_active
            and not page_events_overflowed
        ):
            dialog_observed = False
        off_loopback_redirect = self._off_loopback_redirect_observed
        if isinstance(url, str) and self._off_loopback_redirect(url) is True:
            off_loopback_redirect = True
        elif (
            off_loopback_redirect is not True
            and isinstance(url, str)
            and self._page_monitor_active
            and not page_events_overflowed
        ):
            off_loopback_redirect = self._off_loopback_redirect(url)
        if (
            off_loopback_redirect is None
            and isinstance(self._main_frame_url, str)
            and self._page_monitor_active
            and not page_events_overflowed
        ):
            off_loopback_redirect = self._off_loopback_redirect(self._main_frame_url)
        navigation_redirect = self._navigation_redirect_observed
        if isinstance(url, str) and not self._same_target_route(url):
            navigation_redirect = True
        elif (
            navigation_redirect is not True
            and isinstance(url, str)
            and self._page_monitor_active
            and not page_events_overflowed
        ):
            navigation_redirect = not self._same_target_route(url)
        if (
            navigation_redirect is None
            and isinstance(self._main_frame_url, str)
            and self._page_monitor_active
            and not page_events_overflowed
        ):
            navigation_redirect = not self._same_target_route(self._main_frame_url)
        return {
            "pageOpen": self._page_open,
            "dialogOpen": observed_dialog,
            "dialogObserved": dialog_observed,
            "popupObserved": self._popup_observed,
            "popupAttempted": self._popup_attempted,
            "crashed": self._crashed,
            "offLoopbackRedirect": off_loopback_redirect,
            "navigationRedirect": navigation_redirect,
        }

    def _unobservable_observation(self) -> Dict[str, Any]:
        self._collect_page_events()
        self._refresh_target_state()
        return {
            "url": self._main_frame_url,
            "title": None,
            "focus": {},
            "controls": [],
            "successMatched": False,
            "lifecycle": self._lifecycle(),
        }

    def observe(self) -> Dict[str, Any]:
        if self.connection is None:
            raise BrowserError("browser is not connected")
        self._collect_page_events()
        self._refresh_target_state()
        if self._page_open is False or self._crashed is True:
            return self._unobservable_observation()
        try:
            result = self.connection.call(
                "Runtime.evaluate",
                {"expression": OBSERVATION_SCRIPT, "returnByValue": True, "awaitPromise": True},
            )
        except BrowserError:
            self._mark_page_monitor_unavailable()
            return self._unobservable_observation()
        value = result.get("result", {}).get("value") if isinstance(result, dict) else None
        if not isinstance(value, dict):
            return self._unobservable_observation()
        raw_lifecycle = value.get("lifecycle")
        dialog_open = (
            raw_lifecycle.get("dialogOpen")
            if isinstance(raw_lifecycle, dict)
            and isinstance(raw_lifecycle.get("dialogOpen"), bool)
            else None
        )
        self._collect_page_events()
        self._refresh_target_state()
        if isinstance(value.get("url"), str):
            self._record_main_frame_url(value["url"])
        if dialog_open is True:
            self._dialog_observed = True
        value["lifecycle"] = self._lifecycle(value.get("url"), dialog_open)
        return value

    def _mark_page_monitor_unavailable(self) -> None:
        self._page_monitor_active = False
        self._native_dialog_open = None
        if self._dialog_observed is not True:
            self._dialog_observed = None
        if self._popup_attempted is not True:
            self._popup_attempted = None
        if self._crashed is not True:
            self._crashed = None
        if self._off_loopback_redirect_observed is not True:
            self._off_loopback_redirect_observed = None
        if self._navigation_redirect_observed is not True:
            self._navigation_redirect_observed = None

    def _capture_redacted_screenshot_bytes(self) -> bytes:
        if self.connection is None:
            raise BrowserError("browser is not connected")
        self._preflight_keyboard_action(None)
        bounds_result = self.connection.call(
            "Runtime.evaluate",
            {"expression": EDITABLE_BOUNDS_SCRIPT, "returnByValue": True},
        )
        bounds = bounds_result.get("result", {}).get("value")
        if not isinstance(bounds, list) or not all(isinstance(bound, dict) for bound in bounds):
            raise BrowserError("browser returned no safe screenshot bounds")
        screenshot_result = self.connection.call("Page.captureScreenshot", {"format": "png"})
        encoded = screenshot_result.get("data") if isinstance(screenshot_result, dict) else None
        if not isinstance(encoded, str):
            raise BrowserError("browser returned no screenshot")
        try:
            screenshot = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise BrowserError("browser returned an invalid screenshot") from error
        redacted = _redact_png(screenshot, bounds)
        self._preflight_keyboard_action(None)
        return redacted

    def capture_planner_screenshot(self) -> Optional[str]:
        """Return a bounded redacted PNG data URL for multimodal planner input."""
        try:
            redacted = self._capture_redacted_screenshot_bytes()
        except Exception:
            return None
        if len(redacted) > MAX_PLANNER_SCREENSHOT_BYTES:
            return None
        return "data:image/png;base64," + base64.b64encode(redacted).decode("ascii")

    def capture_redacted_screenshot(self, destination: Path) -> str:
        redacted = self._capture_redacted_screenshot_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(redacted)
        return destination.name

    def press_key(self, key: str) -> None:
        if key not in PERMITTED_KEYS:
            raise BrowserActionError("keyboard action is outside the permitted interaction set")
        if self.connection is None:
            raise BrowserActionError("browser is not connected")
        self._preflight_keyboard_action(key)
        if key == "Shift+Tab":
            events = [
                {
                    "type": "keyDown",
                    "key": "Shift",
                    "code": "ShiftLeft",
                    "windowsVirtualKeyCode": 16,
                    "nativeVirtualKeyCode": 16,
                },
                {
                    "type": "keyDown",
                    "key": "Tab",
                    "code": "Tab",
                    "modifiers": 8,
                    "windowsVirtualKeyCode": 9,
                    "nativeVirtualKeyCode": 9,
                },
                {
                    "type": "keyUp",
                    "key": "Tab",
                    "code": "Tab",
                    "modifiers": 8,
                    "windowsVirtualKeyCode": 9,
                    "nativeVirtualKeyCode": 9,
                },
                {
                    "type": "keyUp",
                    "key": "Shift",
                    "code": "ShiftLeft",
                    "windowsVirtualKeyCode": 16,
                    "nativeVirtualKeyCode": 16,
                },
            ]
        else:
            actual_key = " " if key == "Space" else key
            code = "Space" if key == "Space" else key
            key_code = {
                "Tab": 9,
                "Enter": 13,
                " ": 32,
                "ArrowLeft": 37,
                "ArrowUp": 38,
                "ArrowRight": 39,
                "ArrowDown": 40,
                "Escape": 27,
            }.get(actual_key, 0)
            events = [
                {
                    "type": "keyDown",
                    "key": actual_key,
                    "code": code,
                    "text": "\r" if key == "Enter" else (" " if key == "Space" else ""),
                    "windowsVirtualKeyCode": key_code,
                    "nativeVirtualKeyCode": key_code,
                },
                {
                    "type": "keyUp",
                    "key": actual_key,
                    "code": code,
                    "windowsVirtualKeyCode": key_code,
                    "nativeVirtualKeyCode": key_code,
                },
            ]
        try:
            for event in events:
                self.connection.call("Input.dispatchKeyEvent", event)
            self._wait_for_settled_input()
        except BrowserError as error:
            raise BrowserActionError("keyboard action could not be delivered") from error

    def type_text(self, text: str) -> int:
        if not isinstance(text, str) or not text or len(text) > MAX_TYPED_CHARACTERS:
            raise BrowserActionError("typed input must be bounded plain text")
        if "\n" in text or "\r" in text or "\t" in text:
            raise BrowserActionError("typed input must be single-line plain text")
        if self.connection is None:
            raise BrowserActionError("browser is not connected")
        self._preflight_keyboard_action(None)
        try:
            # Send real key events in one bounded batch. It does not use a
            # clipboard and the raw value never enters the planner context,
            # action record, or browser logs.
            call_ids = []
            for character in text:
                call_ids.append(
                    self.connection.send_call(
                        "Input.dispatchKeyEvent",
                        {"type": "keyDown", "key": character, "text": character},
                    )
                )
                call_ids.append(
                    self.connection.send_call(
                        "Input.dispatchKeyEvent",
                        {"type": "keyUp", "key": character},
                    )
                )
            self.connection.wait_for_calls(call_ids)
            self._wait_for_settled_input()
        except BrowserError as error:
            raise BrowserActionError("bounded text could not be delivered") from error
        return len(text)

    def _preflight_keyboard_action(self, key: Optional[str]) -> None:
        """Avoid delivering keyboard input after leaving the controlled page."""
        if self.connection is None:
            raise BrowserActionError("browser is not connected")
        self._collect_page_events()
        self._refresh_target_state()
        if self._page_open is False or self._crashed is True:
            raise BrowserActionError("controlled browser page is no longer available")
        if self._native_dialog_open is True:
            if key == "Escape" and self._same_target_route(self._main_frame_url or ""):
                lifecycle = self._lifecycle(self._main_frame_url)
                if (
                    lifecycle.get("pageOpen") is True
                    and lifecycle.get("crashed") is False
                    and lifecycle.get("popupObserved") is not None
                    and lifecycle.get("offLoopbackRedirect") is False
                    and lifecycle.get("navigationRedirect") is False
                ):
                    return
            raise BrowserActionError("a browser dialog is blocking keyboard input")
        try:
            result = self.connection.call(
                "Runtime.evaluate",
                {"expression": "String(window.location.href)", "returnByValue": True},
            )
        except BrowserError as error:
            self._mark_page_monitor_unavailable()
            self._collect_page_events()
            self._refresh_target_state()
            raise BrowserActionError(
                "controlled page could not be checked before input"
            ) from error
        current_url = (
            result.get("result", {}).get("value") if isinstance(result, dict) else None
        )
        if not isinstance(current_url, str):
            raise BrowserActionError("controlled page URL was unavailable before input")
        self._record_main_frame_url(current_url)
        self._collect_page_events()
        self._refresh_target_state()
        lifecycle = self._lifecycle(current_url)
        if any(
            lifecycle.get(field) is None
            for field in (
                "pageOpen",
                "dialogOpen",
                "dialogObserved",
                "popupObserved",
                "crashed",
                "offLoopbackRedirect",
                "navigationRedirect",
            )
        ):
            raise BrowserActionError("browser lifecycle could not be verified before input")
        if (
            not self._same_target_route(current_url)
            or lifecycle.get("offLoopbackRedirect")
            or lifecycle.get("navigationRedirect")
        ):
            raise BrowserActionError("browser left the controlled target before input")

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.browser_connection is not None:
            self.browser_connection.close()
            self.browser_connection = None
        cleanup_errors = []
        process = self.process
        if process is not None:
            process_ids = _descendant_process_ids(process.pid) | {process.pid}
            process_errors = []
            for process_id in process_ids:
                try:
                    os.kill(process_id, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except OSError as error:
                    process_errors.append(error)
            deadline = time.monotonic() + 0.75
            while time.monotonic() < deadline and any(
                _is_process_alive(process_id) for process_id in process_ids
            ):
                time.sleep(0.05)
            remaining = {
                process_id
                for process_id in process_ids
                if _is_process_alive(process_id)
            }
            for process_id in remaining:
                try:
                    os.kill(process_id, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as error:
                    process_errors.append(error)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired as error:
                process_errors.append(error)
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline and any(
                _is_process_alive(process_id) for process_id in process_ids
            ):
                time.sleep(0.05)
            remaining = {
                process_id
                for process_id in process_ids
                if _is_process_alive(process_id)
            }
            if remaining:
                cleanup_errors.extend(process_errors)
                cleanup_errors.append(OSError("isolated browser processes remain"))
            self.process = None

        profile_cleanup_error = None
        for _ in range(3):
            if not self.profile_directory.exists():
                break
            try:
                shutil.rmtree(self.profile_directory)
            except OSError as error:
                profile_cleanup_error = error
                time.sleep(0.05)
        if self.profile_directory.exists():
            cleanup_errors.append(
                profile_cleanup_error or OSError("isolated browser profile remains")
            )
        if cleanup_errors:
            raise BrowserCleanupError("isolated browser cleanup could not be verified")
