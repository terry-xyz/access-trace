"""Private real-browser boundary for bounded keyboard journeys.

The journey code never receives a browser handle, selector, script, or page
source.  This adapter exposes only keyboard input and a deliberately bounded
observation of the current page.
"""

import base64
import binascii
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
  const controls = Array.from(document.querySelectorAll("input, textarea, button"))
    .slice(0, 8)
    .map(control);
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
    successMatched,
    lifecycle: {
      pageOpen: true,
      dialogOpen,
      popupObserved: window.opener !== null,
      crashed: false,
      offLoopbackRedirect: false,
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
        self.target_url = target_url
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
                    target_url,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            websocket_url = self._wait_for_page()
            self.connection = _WebSocket(websocket_url)
            self.connection.call("Page.enable")
            self.connection.call("Runtime.enable")
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

    def _wait_for_page(self) -> str:
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
                        and page.get("webSocketDebuggerUrl")
                    ):
                        # The isolated profile has one page. Navigation is
                        # issued explicitly after connecting so an initial
                        # about:blank state cannot become an observation.
                        return page["webSocketDebuggerUrl"]
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
        while time.monotonic() < deadline:
            result = self.connection.call(
                "Runtime.evaluate",
                {"expression": "String(window.location.href)", "returnByValue": True},
            )
            current_url = (
                result.get("result", {}).get("value") if isinstance(result, dict) else None
            )
            if isinstance(current_url, str) and current_url.rstrip("/") == expected_url:
                self._wait_for_settled_input()
                return
            time.sleep(0.05)
        raise BrowserError("isolated browser did not reach the controlled target")

    def observe(self) -> Dict[str, Any]:
        if self.connection is None:
            raise BrowserError("browser is not connected")
        result = self.connection.call(
            "Runtime.evaluate",
            {"expression": OBSERVATION_SCRIPT, "returnByValue": True, "awaitPromise": True},
        )
        value = result.get("result", {}).get("value") if isinstance(result, dict) else None
        if not isinstance(value, dict):
            raise BrowserError("browser returned no bounded observation")
        return value

    def capture_redacted_screenshot(self, destination: Path) -> str:
        if self.connection is None:
            raise BrowserError("browser is not connected")
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
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(redacted)
        return destination.name

    def press_key(self, key: str) -> None:
        if key not in PERMITTED_KEYS:
            raise BrowserActionError("keyboard action is outside the permitted interaction set")
        if self.connection is None:
            raise BrowserActionError("browser is not connected")
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

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
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
