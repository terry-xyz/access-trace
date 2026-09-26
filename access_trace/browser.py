"""Private real-browser boundary for bounded keyboard journeys.

The journey code never receives a browser handle, selector, script, or page
source.  This adapter exposes only keyboard input and a deliberately bounded
observation of the current page.
"""

import base64
import binascii
from collections import deque
import json
import math
import os
import re
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
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlsplit, urlunsplit

from .url_policy import is_browser_error_url, same_web_origin


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
MAX_SITE_DISCOVERY_PAGES = 10_000
BROWSER_STARTUP_TIMEOUT = 15.0
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
WEBRTC_LOCKDOWN_SCRIPT = r"""
(() => {
  for (const name of ["RTCPeerConnection", "webkitRTCPeerConnection"]) {
    Object.defineProperty(globalThis, name, {
      value: undefined,
      configurable: false,
      writable: false,
    });
    if (typeof globalThis[name] !== "undefined") {
      throw new Error("WebRTC is unavailable during local HTML assessment");
    }
  }
  return true;
})()
"""
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
    const labelledBy = node.getAttribute("aria-labelledby");
    if (labelledBy) {
      const root = node.getRootNode();
      const names = labelledBy.split(/\s+/).map((id) => root.getElementById?.(id)?.textContent || "");
      const name = compact(names.join(" "));
      if (name) return name;
    }
    if (node.id) {
      const root = node.getRootNode();
      for (const label of root.querySelectorAll?.("label") || []) {
        if (label.htmlFor === node.id) return compact(label.textContent);
      }
    }
    if (node.labels?.length) return compact(Array.from(node.labels).map((label) => label.textContent).join(" "));
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
      accessibleName: null,
      tag: "body",
      stableId: "document",
      isStable: true
    };
    const editable = node.tagName === "INPUT" || node.tagName === "TEXTAREA";
    const item = {
      role: roleFor(node),
      accessibleName: labelFor(node),
      tag: node.tagName.toLowerCase(),
      // DOM order gives anonymous controls a bounded identity for keyboard
      // traversal without exposing selectors or page text.
      stableId: compact(node.id) || `dom-index-${allControls.indexOf(node) + 1}`,
      isStable: allControls.includes(node),
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
  const focusableSelector = 'a[href], button, input, textarea, select, [tabindex]:not([tabindex="-1"])';
  const composedElements = [];
  const visited = new Set();
  const pending = Array.from(document.childNodes).reverse();
  let traversalTruncated = false;
  while (pending.length) {
    const node = pending.pop();
    if (!node || node.nodeType !== Node.ELEMENT_NODE || visited.has(node)) continue;
    visited.add(node);
    if (visited.size > 50000) {
      traversalTruncated = true;
      break;
    }
    composedElements.push(node);
    let children;
    if (node.tagName === "SLOT") {
      const assigned = node.assignedElements({ flatten: true });
      children = assigned.length ? assigned : Array.from(node.children);
    } else if (node.shadowRoot) {
      children = Array.from(node.shadowRoot.children);
    } else {
      children = Array.from(node.children);
    }
    for (let index = children.length - 1; index >= 0; index -= 1) pending.push(children[index]);
  }
  const allControls = composedElements.filter(
    (node) => node.matches(focusableSelector) && keyboardFocusable(node)
  );
  const controls = allControls.slice(0, 8).map(control);
  let active = document.activeElement || document.body;
  while (active?.shadowRoot?.activeElement) active = active.shadowRoot.activeElement;
  const statuses = composedElements.filter((node) => node.matches('[role="status"]'));
  const dialogOpen = composedElements.filter((node) => node.matches(
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
    controlCount: allControls.length,
    controlsTruncated: traversalTruncated || allControls.length > controls.length,
    pageContentVisible: Boolean(
      (document.body && document.body.innerText.trim())
      || allControls.length
      || composedElements.some((node) =>
        node.matches("img, svg, canvas, video") && visible(node)
      )
    ),
    successMatched,
    lifecycle: {
      dialogOpen,
    },
  };
})()
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
        self.timeout = timeout
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
        self.event_handler = None
        self._checked_command_ids = set()

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
        elif method == "Network.loadingFailed" and params.get("type") == "Document":
            frame_id = params.get("frameId")
            error_text = params.get("errorText")
            if isinstance(frame_id, str) and isinstance(error_text, str):
                self._append_event(
                    {
                        "method": method,
                        "params": {
                            "frameId": frame_id,
                            "errorText": error_text[:80],
                        },
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
        previous_socket_timeout = self.socket.gettimeout()
        total_timeout = self.timeout
        if previous_socket_timeout is not None:
            total_timeout = min(total_timeout, previous_socket_timeout)
        deadline = time.monotonic() + max(0.1, total_timeout)
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BrowserError("browser command timed out")
                # Treat timeout as a total command budget. A noisy page may
                # emit CDP events continuously, so an inactivity timeout alone
                # can otherwise leave a command waiting forever.
                self.socket.settimeout(remaining)
                message = self.receive()
                if isinstance(message.get("method"), str):
                    if callable(self.event_handler):
                        self.event_handler(message)
                    self._remember_event(message)
                    continue
                if message.get("id") != call_id:
                    self._consume_checked_response(message)
                    continue
                if "error" in message:
                    raise BrowserError("browser rejected the requested operation")
                return message.get("result")
        finally:
            self.socket.settimeout(previous_socket_timeout)

    def send_call(self, method: str, params: Optional[Dict[str, Any]] = None) -> int:
        call_id = self._next_call_id
        self._next_call_id += 1
        self.send({"id": call_id, "method": method, "params": params or {}})
        return call_id

    def send_checked_call(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> int:
        call_id = self.send_call(method, params)
        self._checked_command_ids.add(call_id)
        return call_id

    def _consume_checked_response(self, message: Dict[str, Any]) -> None:
        call_id = message.get("id")
        if call_id not in self._checked_command_ids:
            return
        self._checked_command_ids.remove(call_id)
        if "error" in message:
            raise BrowserError("browser rejected the uploaded-page network policy")

    def wait_for_calls(self, call_ids) -> None:
        pending = set(call_ids)
        while pending:
            message = self.receive()
            if isinstance(message.get("method"), str):
                if callable(self.event_handler):
                    self.event_handler(message)
                self._remember_event(message)
                continue
            message_id = message.get("id")
            self._consume_checked_response(message)
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


def _find_chrome() -> Optional[List[str]]:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    executable = next(
        (candidate for candidate in candidates if candidate and Path(candidate).is_file()),
        None,
    )
    if executable is not None:
        return [executable]

    flatpak = shutil.which("flatpak")
    if flatpak is None:
        return None
    try:
        installed = subprocess.run(
            [flatpak, "info", "org.chromium.Chromium"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if installed.returncode == 0:
        return [flatpak, "run", "--command=chromium", "org.chromium.Chromium"]
    return None


def _process_ids_using_profile(profile_directory: Path):
    # Flatpak can reparent its wrapper to the portal, so the unique profile is its identity.
    profile_argument = "--user-data-dir={0}".format(profile_directory)
    try:
        output = subprocess.check_output(
            ["ps", "-axo", "pid=,args="], text=True, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise BrowserCleanupError(
            "isolated browser process cleanup could not be checked"
        ) from error
    process_ids = set()
    for line in output.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) != 2 or profile_argument not in fields[1].split():
            continue
        try:
            process_ids.add(int(fields[0]))
        except ValueError:
            continue
    return process_ids


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


class _UploadedPageRequestPolicy:
    """Allow the uploaded document and its local assets; deny other network use."""

    def __init__(
        self,
        connection: _WebSocket,
        target_url: str,
        main_frame_id: Optional[str],
        allow_site_documents: bool = False,
    ):
        self.connection = connection
        self.target = urlsplit(target_url)
        site_match = re.match(r"^(/sites/[0-9a-f]{32})/", self.target.path)
        self.site_prefix = site_match.group(1) + "/" if site_match else ""
        self.main_frame_id = main_frame_id
        self.allow_site_documents = allow_site_documents
        self.initial_document_allowed = False

    def _allows_request(
        self,
        url: Any,
        method: Any,
        resource_type: Any,
        frame_id: Any,
    ) -> bool:
        if (
            self.main_frame_id is None
            or frame_id != self.main_frame_id
            or method != "GET"
            or not isinstance(url, str)
        ):
            return False
        try:
            request = urlsplit(url)
            request_port = request.port or (80 if request.scheme == "http" else 443)
            target_port = self.target.port or (
                80 if self.target.scheme == "http" else 443
            )
        except ValueError:
            return False
        same_origin = (
            request.scheme == self.target.scheme
            and request.hostname == self.target.hostname
            and request_port == target_port
            and not request.username
            and not request.password
        )
        if not same_origin:
            return False
        if resource_type == "Document":
            matches_target = (
                not self.initial_document_allowed
                and request.path == self.target.path
                and request.query == self.target.query
            )
            if not matches_target and self.allow_site_documents and self.site_prefix:
                relative = unquote(request.path[len(self.site_prefix):]) if request.path.startswith(self.site_prefix) else ""
                parts = relative.rstrip("/").split("/")
                matches_target = bool(relative) and not any(
                    part in {"", ".", ".."} for part in parts
                )
            if not matches_target:
                return False
            # Consume the sole allow before continuing it: if CDP handling fails,
            # any retry or subsequent navigation remains blocked.
            self.initial_document_allowed = True
            return True
        if resource_type not in {"Script", "Stylesheet", "Image", "Font", "Media", "Other"}:
            return False
        if not self.site_prefix or not request.path.startswith(self.site_prefix):
            return False
        relative = unquote(request.path[len(self.site_prefix) :])
        parts = relative.split("/")
        return bool(relative) and not any(part in {"", ".", ".."} for part in parts)

    def handle_event(self, message: Dict[str, Any]) -> None:
        if message.get("method") != "Fetch.requestPaused":
            return
        params = message.get("params")
        if not isinstance(params, dict):
            raise BrowserError("browser paused a request without policy details")
        request_id = params.get("requestId")
        request = params.get("request")
        if not isinstance(request_id, str) or not isinstance(request, dict):
            raise BrowserError("browser paused a request without a request identifier")

        is_request_stage = (
            "responseStatusCode" not in params
            and "responseErrorReason" not in params
        )
        if is_request_stage and self._allows_request(
            request.get("url"),
            request.get("method"),
            params.get("resourceType"),
            params.get("frameId"),
        ):
            self.connection.send_checked_call(
                "Fetch.continueRequest", {"requestId": request_id}
            )
            return
        # Fetch pauses before the browser sends the request. Redirect follow-ups,
        # reloads, form submissions, popups, and subresources are all denied.
        self.connection.send_checked_call(
            "Fetch.failRequest",
            {"requestId": request_id, "errorReason": "BlockedByClient"},
        )


class IsolatedKeyboardBrowser:
    """A fresh, keyboard-only Chrome session with bounded observations."""

    def __init__(
        self,
        target_url: str,
        restrict_network: bool = False,
        allow_site_navigation: bool = False,
        headless: bool = True,
    ):
        chrome_command = _find_chrome()
        if chrome_command is None:
            raise BrowserError(
                "Install Google Chrome or Chromium, or install the "
                "org.chromium.Chromium Flatpak"
            )
        self.profile_directory = Path(tempfile.mkdtemp(prefix="access-trace-browser-"))
        self.process: Optional[subprocess.Popen] = None
        self.connection: Optional[_WebSocket] = None
        self.browser_connection: Optional[_WebSocket] = None
        self.target_url = target_url
        self.headless = headless
        self._www_host_fallback = False
        navigation_url = target_url
        if not restrict_network:
            navigation_url = self._www_fallback_after_dns_failure(target_url)
            self._www_host_fallback = navigation_url != target_url
        self.restrict_network = restrict_network
        self.allow_site_navigation = allow_site_navigation
        self.request_policy: Optional[_UploadedPageRequestPolicy] = None
        self.target_id: Optional[str] = None
        self._page_monitor_active = False
        self._main_frame_id: Optional[str] = None
        self._page_open: Optional[bool] = None
        self._dom_dialog_open: Optional[bool] = None
        self._popup_observed: Optional[bool] = None
        self._popup_attempted: Optional[bool] = None
        self._crashed: Optional[bool] = None
        self._native_dialog_open: Optional[bool] = None
        self._dialog_observed: Optional[bool] = None
        self._off_loopback_redirect_observed: Optional[bool] = None
        self._navigation_redirect_observed: Optional[bool] = None
        self._browser_load_error_observed: Optional[bool] = None
        self._main_frame_url: Optional[str] = None
        self._navigation_started = False
        self._page_content_visible: Optional[bool] = None
        self._accessibility_tree_nodes: Optional[int] = None
        self._observation_sequence = 0
        self._focus_observation_count = 0
        self._page_title = ""
        self._accessibility_snapshot_cache: Optional[Dict[str, Any]] = None
        self.debug_port = self._free_port()
        try:
            chrome_options = [
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
            ]
            if headless:
                chrome_options.insert(0, "--headless=new")
            if self.restrict_network:
                chrome_options.extend(
                    ["--dns-prefetch-disable", "--disable-preconnect"]
                )
            chrome_arguments = [*chrome_command, *chrome_options]
            self.process = subprocess.Popen(
                chrome_arguments,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            browser_websocket_url = self._wait_for_browser()
            websocket_timeout = 10.0
            self.browser_connection = _WebSocket(
                browser_websocket_url, timeout=websocket_timeout
            )
            self.browser_connection.call(
                "Target.setDiscoverTargets", {"discover": True}
            )
            target_id, websocket_url = self._wait_for_page()
            self.target_id = target_id
            self.connection = _WebSocket(websocket_url, timeout=websocket_timeout)
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
            if self.restrict_network:
                self._install_uploaded_page_webrtc_lockdown()
                self.request_policy = _UploadedPageRequestPolicy(
                    self.connection,
                    target_url,
                    self._main_frame_id,
                    allow_site_documents=allow_site_navigation,
                )
                self.connection.event_handler = self.request_policy.handle_event
                self.connection.call(
                    "Fetch.enable",
                    {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]},
                )
            self._page_monitor_active = True
            self._popup_attempted = False
            self._native_dialog_open = False
            self._crashed = False
            self._refresh_target_state()
            self._navigation_started = True
            self.connection.call("Page.navigate", {"url": navigation_url})
            self._wait_for_target(timeout=12.0 if not headless else 8.0)
            if not headless:
                self._wait_for_rendered_content(timeout=10.0)
        except Exception as error:
            try:
                self.close()
            except BrowserCleanupError as cleanup_error:
                raise BrowserCleanupError(
                    "isolated browser startup cleanup could not be verified"
                ) from cleanup_error
            detail = str(error).strip()
            message = "unable to start the isolated browser"
            if detail:
                message += ": " + detail[:160]
            raise BrowserError(message) from error

    def _install_uploaded_page_webrtc_lockdown(self) -> None:
        if self.connection is None:
            raise BrowserError("browser is not connected")
        installed = self.connection.call(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": WEBRTC_LOCKDOWN_SCRIPT},
        )
        if not isinstance(installed, dict) or not isinstance(
            installed.get("identifier"), str
        ):
            raise BrowserError("browser could not install the WebRTC lockdown")

        current_document = self.connection.call(
            "Runtime.evaluate",
            {
                "expression": WEBRTC_LOCKDOWN_SCRIPT,
                "returnByValue": True,
                "awaitPromise": False,
            },
        )
        result = (
            current_document.get("result", {}).get("value")
            if isinstance(current_document, dict)
            else None
        )
        if (
            not isinstance(current_document, dict)
            or current_document.get("exceptionDetails") is not None
            or result is not True
        ):
            raise BrowserError("browser could not apply the WebRTC lockdown")

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as source:
            source.bind(("127.0.0.1", 0))
            return int(source.getsockname()[1])

    def _wait_for_browser(self) -> str:
        deadline = time.monotonic() + BROWSER_STARTUP_TIMEOUT
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
        deadline = time.monotonic() + BROWSER_STARTUP_TIMEOUT
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

    def _wait_for_rendered_content(self, timeout: float = 10.0) -> None:
        """Give headed pages up to ten seconds to expose rendered content."""
        if self.connection is None:
            raise BrowserError("browser is not connected")
        deadline = time.monotonic() + max(0.1, min(timeout, 10.0))
        expression = """(() => {
          const visible = (element) => {
            if (!element || element.getClientRects().length === 0) return false;
            const style = getComputedStyle(element);
            return style.display !== 'none' && style.visibility !== 'hidden'
              && Number(style.opacity) !== 0;
          };
          const text = (document.body && document.body.innerText || '').trim();
          const controls = document.querySelectorAll(
            'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
          );
          const media = document.querySelectorAll('img, svg, canvas, video');
          return Boolean(text || Array.from(controls).some(visible)
            || Array.from(media).some(visible));
        })()"""
        while time.monotonic() < deadline:
            remaining = max(0.1, deadline - time.monotonic())
            try:
                self.connection.socket.settimeout(min(1.0, remaining))
                result = self.connection.call(
                    "Runtime.evaluate",
                    {
                        "expression": expression,
                        "returnByValue": True,
                        "timeout": min(800.0, remaining * 1000),
                    },
                )
                value = (
                    result.get("result", {}).get("value")
                    if isinstance(result, dict)
                    else None
                )
                if value is True:
                    return
            except BrowserError:
                self._refresh_target_state()
                if self._page_open is False or self._crashed is True:
                    return
            finally:
                self.connection.socket.settimeout(self.connection.timeout)
            self._collect_page_events()
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))

    def _wait_for_target(
        self, timeout: float = 8.0, expected_url: Optional[str] = None
    ) -> None:
        if self.connection is None:
            raise BrowserError("browser is not connected")
        expected_url = (expected_url or self.target_url).rstrip("/")
        deadline = time.monotonic() + max(0.5, min(timeout, 20.0))
        previous_url = None
        stable_observations = 0
        while time.monotonic() < deadline:
            try:
                remaining = max(0.1, deadline - time.monotonic())
                self.connection.socket.settimeout(min(2.0, remaining))
                result = self.connection.call(
                    "Runtime.evaluate",
                    {
                        "expression": "({url: String(window.location.href), readyState: document.readyState})",
                        "returnByValue": True,
                        "timeout": min(1500.0, remaining * 1000),
                    },
                )
            except BrowserError:
                self._refresh_target_state()
                if self._page_open is False or self._crashed is True:
                    return
                time.sleep(0.05)
                continue
            finally:
                self.connection.socket.settimeout(self.connection.timeout)
            state = result.get("result", {}).get("value") if isinstance(result, dict) else None
            current_url = state.get("url") if isinstance(state, dict) else None
            ready_state = state.get("readyState") if isinstance(state, dict) else None
            self._collect_page_events()
            if (
                isinstance(current_url, str)
                and current_url.rstrip("/") == expected_url
                and ready_state in {"interactive", "complete"}
            ):
                self._wait_for_settled_input()
                return
            if (
                isinstance(current_url, str)
                and current_url not in {"", "about:blank"}
                and ready_state in {"interactive", "complete"}
            ):
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
            elif method == "Network.loadingFailed":
                error_text = params.get("errorText") if isinstance(params, dict) else None
                if (
                    isinstance(params, dict)
                    and params.get("frameId") in main_frame_ids
                    and isinstance(error_text, str)
                    and error_text.startswith("net::ERR_")
                    and error_text != "net::ERR_ABORTED"
                ):
                    self._browser_load_error_observed = True
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
        if is_browser_error_url(url):
            self._browser_load_error_observed = True
            return
        if self._browser_load_error_observed is not True:
            self._browser_load_error_observed = False
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
        same_origin = (
            same_web_origin(target, observed)
            and not observed.username
            and not observed.password
        )
        if not same_origin:
            return False
        if target.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return True
        return (
            observed.scheme == target.scheme
            and observed.hostname in {"localhost", "127.0.0.1", "::1"}
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
        if is_browser_error_url(url):
            return False
        try:
            observed = urlsplit(url[:4096])
        except ValueError:
            return None
        if observed.hostname is None:
            return None
        target = urlsplit(self.target_url)
        try:
            observed_port = observed.port or (443 if observed.scheme == "https" else 80)
            target_port = target.port or (443 if target.scheme == "https" else 80)
        except ValueError:
            return True
        if target.hostname in LOOPBACK_HOSTS:
            same_origin = (
                observed.scheme == target.scheme
                and observed.hostname in LOOPBACK_HOSTS
                and observed_port == target_port
            )
        else:
            same_origin = same_web_origin(target, observed)
        return not (same_origin and not observed.username and not observed.password)

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
        browser_load_error = (
            self._browser_load_error_observed is True or is_browser_error_url(url)
        )
        if browser_load_error:
            self._browser_load_error_observed = True
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
        if browser_load_error:
            off_loopback_redirect = False
            navigation_redirect = False
        return {
            "pageOpen": self._page_open,
            "dialogOpen": observed_dialog,
            "dialogObserved": dialog_observed,
            "popupObserved": self._popup_observed,
            "popupAttempted": self._popup_attempted,
            "crashed": self._crashed,
            "offLoopbackRedirect": off_loopback_redirect,
            "navigationRedirect": navigation_redirect,
            "browserLoadError": browser_load_error,
            "wwwHostFallback": self._www_host_fallback,
            "pageContentVisible": self._page_content_visible,
            "headfulFallback": not self.headless,
        }

    @staticmethod
    def _www_fallback_after_dns_failure(target_url: str) -> str:
        """Try a www alias only when the submitted hostname itself fails DNS."""
        try:
            target = urlsplit(target_url)
            host = target.hostname
            if (
                target.scheme not in {"http", "https"}
                or not host
                or host.lower().startswith("www.")
                or host in LOOPBACK_HOSTS
                or target.username
                or target.password
            ):
                return target_url
            port = target.port or (443 if target.scheme == "https" else 80)
            socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            return target_url
        except socket.gaierror:
            pass
        except (ValueError, OSError):
            return target_url
        fallback_host = "www." + host
        try:
            socket.getaddrinfo(fallback_host, port, type=socket.SOCK_STREAM)
        except (socket.gaierror, OSError):
            return target_url
        netloc = fallback_host
        if target.port is not None:
            netloc += ":" + str(target.port)
        return urlunsplit((target.scheme, netloc, target.path, target.query, target.fragment))

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

    def _accessibility_snapshot(self) -> Optional[Dict[str, Any]]:
        """Extract a bounded focusable-control view from Chrome's AX tree."""
        if self.connection is None:
            return None
        try:
            result = self.connection.call(
                "Accessibility.getFullAXTree", {"depth": 24}
            )
        except BrowserError:
            return None
        nodes = result.get("nodes") if isinstance(result, dict) else None
        if not isinstance(nodes, list):
            return None
        self._accessibility_tree_nodes = len(nodes)
        focusable_nodes = []
        focused_node = None
        content_visible = False
        for node in nodes[:20_000]:
            if not isinstance(node, dict):
                continue
            role = node.get("role", {}).get("value") if isinstance(node.get("role"), dict) else None
            name = node.get("name", {}).get("value") if isinstance(node.get("name"), dict) else None
            role = role[:80] if isinstance(role, str) else None
            name = name[:80] if isinstance(name, str) else None
            properties = node.get("properties", [])
            prop_map = {
                item.get("name"): item.get("value", {}).get("value")
                for item in properties
                if isinstance(item, dict) and isinstance(item.get("value"), dict)
            } if isinstance(properties, list) else {}
            # Landmarks (and the document title copied onto RootWebArea) can
            # survive in Chrome's AX tree even when the rendered page is
            # completely empty. Count actual text or user-operable content,
            # rather than any named AX node, as page content.
            if (
                node.get("ignored") is not True
                and name
                and role in {
                    "heading", "staticText", "text", "paragraph", "link",
                    "button", "checkbox", "radioButton", "textbox",
                    "searchBox", "menuItem", "tab", "listMarker", "cell",
                }
            ):
                content_visible = True
            backend_id = node.get("backendDOMNodeId")
            stable_id = (
                "ax-dom-" + str(backend_id)
                if isinstance(backend_id, int) and not isinstance(backend_id, bool)
                else None
            )
            if (
                prop_map.get("focused") is True
                and stable_id
                and role not in {None, "none", "RootWebArea", "WebArea"}
            ):
                focused_node = (backend_id, stable_id, role, name)
            if (
                prop_map.get("focusable") is not True
                or not stable_id
                or role in {None, "none", "RootWebArea", "WebArea"}
                or node.get("ignored") is True
            ):
                continue
            focusable_nodes.append((backend_id, stable_id, role, name))
            if len(focusable_nodes) >= 10_000:
                break

        def describe_tag(backend_id):
            original_timeout = self.connection.timeout
            try:
                self.connection.socket.settimeout(min(1.0, original_timeout))
                described = self.connection.call(
                    "DOM.describeNode",
                    {"backendNodeId": backend_id, "depth": 0, "pierce": True},
                )
                dom_node = described.get("node") if isinstance(described, dict) else None
                tag = dom_node.get("nodeName") if isinstance(dom_node, dict) else None
                return tag.lower() if isinstance(tag, str) else "generic"
            except BrowserError:
                return "generic"
            finally:
                self.connection.socket.settimeout(original_timeout)

        controls = []
        for backend_id, stable_id, role, name in focusable_nodes[:8]:
            tag = describe_tag(backend_id)
            control = {
                "role": role,
                "accessibleName": name,
                "tag": tag,
                "stableId": stable_id,
                "isStable": True,
                "focusable": True,
            }
            if role == "textbox" and tag in {"input", "textarea"}:
                control.update(
                    characterCount=0,
                    acceptedInput=None,
                    validationState="not-observed",
                )
            controls.append(control)
        focused = None
        if focused_node is not None:
            backend_id, stable_id, role, name = focused_node
            tag = next(
                (item["tag"] for item in controls if item["stableId"] == stable_id),
                describe_tag(backend_id),
            )
            focused = {
                "role": role,
                "accessibleName": name,
                "tag": tag,
                "stableId": stable_id,
                "isStable": True,
                "focusable": True,
                "characterCount": 0,
                "acceptedInput": None,
                "validationState": "not-observed",
            }
            if role == "textbox" and tag in {"input", "textarea"}:
                focused["characterCount"] = 0
        return {
            "controls": controls,
            "controlCount": len(focusable_nodes),
            "controlsTruncated": len(focusable_nodes) > 8,
            "focus": focused,
            "pageContentVisible": content_visible or bool(controls),
            "treeNodeCount": len(nodes),
        }

    def needs_headful_retry(self) -> bool:
        """Detect a publicly loaded page that headless Chrome barely rendered."""
        return self._page_content_visible is False or (
            self._accessibility_tree_nodes is not None
            and self._accessibility_tree_nodes <= 2
        )

    def discover_site_links(self) -> List[str]:
        """Return bounded same-origin document links for whole-site traversal."""
        if self.connection is None:
            raise BrowserError("browser is not connected")
        result = self.connection.call(
            "Runtime.evaluate",
            {
                "expression": """(() => {
                  const origin = location.origin;
                  const links = [];
                  const seen = new Set();
                  const nodes = [];
                  const visited = new Set();
                  const pending = Array.from(document.childNodes).reverse();
                  while (pending.length && visited.size < 50000) {
                    const node = pending.pop();
                    if (!node || node.nodeType !== Node.ELEMENT_NODE || visited.has(node)) continue;
                    visited.add(node);
                    nodes.push(node);
                    let children;
                    if (node.tagName === 'SLOT') {
                      const assigned = node.assignedElements({flatten: true});
                      children = assigned.length ? assigned : Array.from(node.children);
                    } else if (node.shadowRoot) {
                      children = Array.from(node.shadowRoot.children);
                    } else {
                      children = Array.from(node.children);
                    }
                    for (let index = children.length - 1; index >= 0; index -= 1) pending.push(children[index]);
                  }
                  for (const anchor of nodes.filter(node => node.tagName === 'A' && node.hasAttribute('href'))) {
                    try {
                      const url = new URL(anchor.href, location.href);
                      if (url.origin !== origin || !['http:', 'https:'].includes(url.protocol)) continue;
                      if (/\.(?:pdf|zip|gz|tar|7z|rar|png|jpe?g|gif|webp|svg|mp[34]|wav|woff2?|ttf|css|js|mjs|json)$/i.test(url.pathname)) continue;
                      url.hash = '';
                      const value = url.href;
                      if (!seen.has(value)) { seen.add(value); links.push(value); }
                    } catch {}
                  }
                  return links;
                })()""",
                "returnByValue": True,
            },
        )
        values = result.get("result", {}).get("value") if isinstance(result, dict) else None
        if not isinstance(values, list):
            return []
        target = urlsplit(self.target_url)
        links = []
        seen = set()
        for value in values:
            if not isinstance(value, str):
                continue
            try:
                observed = urlsplit(value)
                if (
                    not same_web_origin(target, observed)
                    or observed.username
                    or observed.password
                    or is_browser_error_url(value)
                ):
                    continue
                # Queries often contain session or personal data. Traversal
                # follows the page path only and never persists link URLs.
                safe_url = urlunsplit((observed.scheme, observed.netloc, observed.path or "/", "", ""))
            except ValueError:
                continue
            if safe_url not in seen:
                seen.add(safe_url)
                links.append(safe_url)
        return links

    def crawl_site_pages(self, max_pages: int = MAX_SITE_DISCOVERY_PAGES) -> Dict[str, Any]:
        """Discover same-origin pages before any keyboard audit begins.

        Prefer robots.txt and sitemap files for fast complete discovery, then
        add same-origin links scraped from the current page. Linked pages are
        never opened during discovery; the journey applies its configured page
        limit only after this URL list is ready.
        """
        if self.connection is None:
            raise BrowserError("browser is not connected")
        try:
            bounded_page_limit = int(max_pages)
        except (TypeError, ValueError, OverflowError):
            bounded_page_limit = MAX_SITE_DISCOVERY_PAGES
        bounded_page_limit = max(1, min(bounded_page_limit, MAX_SITE_DISCOVERY_PAGES))
        result = self.connection.call(
            "Runtime.evaluate",
            {
                "expression": r"""(async () => {
                  const origin = location.origin;
                  const maxPages = 10000;
                  const maxSitemaps = 64;
                  const deadline = performance.now() + 7500;
                  const excluded = /\.(?:pdf|zip|gz|tar|7z|rar|png|jpe?g|gif|webp|svg|mp[34]|wav|woff2?|ttf|css|js|mjs|json|xml)$/i;
                  const canonical = value => {
                    try {
                      const url = new URL(value, location.href);
                      if (url.origin !== origin || !["http:", "https:"].includes(url.protocol)) return null;
                      if (url.username || url.password || excluded.test(url.pathname)) return null;
                      url.search = "";
                      url.hash = "";
                      return url.href;
                    } catch { return null; }
                  };
                  const pages = [];
                  const seenPages = new Set();
                  const addPage = value => {
                    const page = canonical(value);
                    if (!page || seenPages.has(page) || pages.length >= maxPages) return null;
                    seenPages.add(page);
                    pages.push(page);
                    return page;
                  };
                  const readLimited = async response => {
                    const reader = response.body?.getReader();
                    if (!reader) return "";
                    const chunks = [];
                    let length = 0;
                    while (length < 1500000) {
                      const {value, done} = await reader.read();
                      if (done) break;
                      const chunk = value.subarray(0, 1500000 - length);
                      chunks.push(chunk);
                      length += chunk.length;
                      if (chunk.length !== value.length) { await reader.cancel(); break; }
                    }
                    const bytes = new Uint8Array(length);
                    let offset = 0;
                    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
                    return new TextDecoder().decode(bytes);
                  };
                  const fetchText = async value => {
                    const controller = new AbortController();
                    const timer = setTimeout(() => controller.abort(), 2200);
                    try {
                      const response = await fetch(value, {
                        credentials: "omit", cache: "no-store", redirect: "follow",
                        signal: controller.signal,
                        headers: {Accept: "text/html, application/xml, text/xml, text/plain;q=0.9"},
                      });
                      if (!response.ok || new URL(response.url).origin !== origin) return null;
                      return {url: response.url, type: response.headers.get("content-type") || "", text: await readLimited(response)};
                    } catch { return null; }
                    finally { clearTimeout(timer); }
                  };
                  addPage(location.href);
                  const sitemapQueue = [];
                  const sitemapSeen = new Set();
                  const robots = await fetchText(new URL("/robots.txt", location.href).href);
                  if (robots?.text) {
                    for (const line of robots.text.split(/\r?\n/)) {
                      const match = /^\s*sitemap\s*:\s*(\S+)/i.exec(line);
                      const sitemap = match && canonical(match[1]);
                      if (sitemap) sitemapQueue.push(sitemap);
                    }
                  }
                  if (!sitemapQueue.length) {
                    sitemapQueue.push(new URL("/sitemap.xml", location.href).href);
                    sitemapQueue.push(new URL("/sitemap_index.xml", location.href).href);
                  }
                  while (sitemapQueue.length && sitemapSeen.size < maxSitemaps && performance.now() < deadline) {
                    const sitemap = sitemapQueue.shift();
                    if (!sitemap || sitemapSeen.has(sitemap)) continue;
                    sitemapSeen.add(sitemap);
                    const response = await fetchText(sitemap);
                    if (!response || !/xml|text/i.test(response.type)) continue;
                    const xml = new DOMParser().parseFromString(response.text, "application/xml");
                    if (xml.querySelector("parsererror")) continue;
                    const isIndex = xml.documentElement?.localName === "sitemapindex";
                    for (const node of xml.getElementsByTagNameNS("*", "loc")) {
                      const value = node.textContent?.trim();
                      if (!value) continue;
                      if (isIndex) {
                        const nested = canonical(value);
                        if (nested && !sitemapSeen.has(nested)) sitemapQueue.push(nested);
                      } else addPage(value);
                      if (pages.length >= maxPages) break;
                    }
                  }
                  const hasSitemap = pages.length > 1;
                  const pendingNodes = Array.from(document.childNodes).reverse();
                  const seenNodes = new Set();
                  while (pendingNodes.length && seenNodes.size < 50000 && pages.length < maxPages) {
                    const node = pendingNodes.pop();
                    if (!node || node.nodeType !== Node.ELEMENT_NODE || seenNodes.has(node)) continue;
                    seenNodes.add(node);
                    if (node.tagName === "A" && node.hasAttribute("href")) {
                      try { addPage(new URL(node.getAttribute("href"), location.href).href); } catch {}
                    }
                    let children;
                    if (node.tagName === "SLOT") {
                      const assigned = node.assignedElements({flatten: true});
                      children = assigned.length ? assigned : Array.from(node.children);
                    } else if (node.shadowRoot) children = Array.from(node.shadowRoot.children);
                    else children = Array.from(node.children);
                    for (let index = children.length - 1; index >= 0; index -= 1) pendingNodes.push(children[index]);
                  }
                  return {
                    pages,
                    source: hasSitemap ? "sitemap" : "page-links",
                    truncated: pages.length >= maxPages || sitemapQueue.length > 0 || seenNodes.size >= 50000,
                  };
                })()""".replace(
                    "const maxPages = 10000;",
                    "const maxPages = {0};".format(bounded_page_limit),
                ),
                "returnByValue": True,
                "awaitPromise": True,
                "timeout": 8_000,
            },
        )
        value = result.get("result", {}).get("value") if isinstance(result, dict) else None
        if not isinstance(value, dict) or not isinstance(value.get("pages"), list):
            raise BrowserError("site page discovery returned no page list")
        target = urlsplit(self.target_url)
        pages = []
        seen = set()
        for page in value["pages"]:
            if not isinstance(page, str):
                continue
            try:
                observed = urlsplit(page)
                if (
                    not same_web_origin(target, observed)
                    or observed.username
                    or observed.password
                    or is_browser_error_url(page)
                ):
                    continue
                safe_url = urlunsplit((observed.scheme, observed.netloc, observed.path or "/", "", ""))
            except ValueError:
                continue
            if safe_url not in seen:
                seen.add(safe_url)
                pages.append(safe_url)
        return {
            "pages": pages,
            "source": value.get("source") if value.get("source") in {"sitemap", "page-links"} else "page-links",
            # Reaching the developer's configured cap is intentional; report
            # truncation only when the independent all-pages safety cap wins.
            "truncated": (
                value.get("truncated") is True
                and bounded_page_limit >= MAX_SITE_DISCOVERY_PAGES
            ),
        }

    def navigate_to(self, url: str) -> None:
        """Navigate only to a vetted page on the selected web origin."""
        if self.connection is None:
            raise BrowserError("browser is not connected")
        try:
            target = urlsplit(self.target_url)
            observed = urlsplit(url)
        except (TypeError, ValueError) as error:
            raise BrowserError("site link was not a valid URL") from error
        if (
            not same_web_origin(target, observed)
            or observed.username
            or observed.password
            or observed.scheme not in {"http", "https"}
        ):
            raise BrowserError("site traversal was blocked outside the selected origin")
        result = self.connection.call("Page.navigate", {"url": url})
        if isinstance(result, dict) and result.get("errorText"):
            raise BrowserError("site page could not be opened")
        self._navigation_started = True
        self._navigation_redirect_observed = False
        self._off_loopback_redirect_observed = None
        self._browser_load_error_observed = False
        self._wait_for_target(expected_url=url)
        if not self.headless:
            # Startup waits for visible content in headed Chrome, but each
            # subsequently selected site page needs the same readiness check.
            # This returns as soon as content appears and is capped at 10s.
            self._wait_for_rendered_content(timeout=10.0)

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
        self._page_title = value.get("title", "") if isinstance(value.get("title"), str) else ""
        raw_lifecycle = value.get("lifecycle")
        self._observation_sequence += 1
        refresh_accessibility = self._accessibility_snapshot_cache is None
        if refresh_accessibility:
            accessibility = self._accessibility_snapshot()
            if accessibility is not None:
                self._accessibility_snapshot_cache = {
                    **accessibility,
                    "focus": None,
                }
        else:
            accessibility = {
                **self._accessibility_snapshot_cache,
                "focus": None,
                "pageContentVisible": False,
            }
        self._page_content_visible = (
            value.get("pageContentVisible")
            if isinstance(value.get("pageContentVisible"), bool)
            else None
        )
        if accessibility is not None:
            if accessibility["controls"]:
                value["controls"] = accessibility["controls"][:8]
                value["controlCount"] = accessibility["controlCount"]
                value["controlsTruncated"] = accessibility["controlsTruncated"]
            if accessibility["focus"] is not None:
                value["focus"] = accessibility["focus"]
            if accessibility["pageContentVisible"]:
                value["pageContentVisible"] = True
                self._page_content_visible = True
        value["accessibilityTreeNodeCount"] = (
            accessibility.get("treeNodeCount") if accessibility is not None else None
        )
        dialog_open = (
            raw_lifecycle.get("dialogOpen")
            if isinstance(raw_lifecycle, dict)
            and isinstance(raw_lifecycle.get("dialogOpen"), bool)
            else None
        )
        self._dom_dialog_open = dialog_open
        self._collect_page_events()
        self._refresh_target_state()
        if isinstance(value.get("url"), str):
            self._record_main_frame_url(value["url"])
        if dialog_open is True:
            self._dialog_observed = True
        value["lifecycle"] = self._lifecycle(value.get("url"), dialog_open)
        return value

    def observe_focus(self) -> Dict[str, Any]:
        """Read the active AX node cheaply after a whole-site Tab action."""
        if self.connection is None:
            raise BrowserError("browser is not connected")
        self._focus_observation_count += 1
        if self._accessibility_snapshot_cache is None:
            return self.observe()

        self._collect_page_events()
        self._collect_target_events()
        try:
            evaluated = self.connection.call(
                "Runtime.evaluate",
                {
                    "expression": "(() => { let node = document.activeElement; while (node && node.shadowRoot && node.shadowRoot.activeElement) node = node.shadowRoot.activeElement; return node; })()",
                    "returnByValue": False,
                },
            )
            result = evaluated.get("result", {}) if isinstance(evaluated, dict) else {}
            object_id = result.get("objectId") if isinstance(result, dict) else None
            if not isinstance(object_id, str):
                raise BrowserError("focused page node was unavailable")
            try:
                partial = self.connection.call(
                    "Accessibility.getPartialAXTree",
                    {"objectId": object_id, "fetchRelatives": False},
                )
            finally:
                try:
                    self.connection.call("Runtime.releaseObject", {"objectId": object_id})
                except BrowserError:
                    pass
        except BrowserError:
            return self.observe()

        nodes = partial.get("nodes") if isinstance(partial, dict) else None
        ax_node = next(
            (
                node for node in nodes or []
                if isinstance(node, dict) and node.get("ignored") is not True
            ),
            None,
        )
        role_data = ax_node.get("role") if isinstance(ax_node, dict) else None
        name_data = ax_node.get("name") if isinstance(ax_node, dict) else None
        role = role_data.get("value") if isinstance(role_data, dict) else None
        name = name_data.get("value") if isinstance(name_data, dict) else None
        backend_id = ax_node.get("backendDOMNodeId") if isinstance(ax_node, dict) else None
        if role == "RootWebArea" or role in {None, "none"}:
            focus = {
                "role": "document",
                "accessibleName": None,
                "tag": "body",
                "stableId": "document",
                "isStable": True,
            }
        else:
            stable_id = (
                "ax-dom-" + str(backend_id)
                if isinstance(backend_id, int) and not isinstance(backend_id, bool)
                else "document"
            )
            tag = next(
                (
                    item.get("tag")
                    for item in self._accessibility_snapshot_cache.get("controls", [])
                    if isinstance(item, dict) and item.get("stableId") == stable_id
                ),
                "generic",
            )
            if (
                tag == "generic"
                and isinstance(backend_id, int)
                and role in {"textbox", "searchBox", "combobox"}
            ):
                try:
                    described = self.connection.call(
                        "DOM.describeNode",
                        {"backendNodeId": backend_id, "depth": 0, "pierce": True},
                    )
                    dom_node = described.get("node") if isinstance(described, dict) else None
                    node_name = dom_node.get("nodeName") if isinstance(dom_node, dict) else None
                    if isinstance(node_name, str):
                        tag = node_name.lower()
                except BrowserError:
                    pass
            focus = {
                "role": role[:80] if isinstance(role, str) else "generic",
                "accessibleName": name[:80] if isinstance(name, str) else None,
                "tag": tag,
                "stableId": stable_id,
                "isStable": isinstance(backend_id, int) and not isinstance(backend_id, bool),
                "focusable": True,
            }
            if focus["role"] == "textbox":
                focus.update(
                    characterCount=0,
                    acceptedInput=None,
                    validationState="not-observed",
                )

        cache = self._accessibility_snapshot_cache
        page_url = self._main_frame_url or self.target_url
        return {
            "url": page_url,
            "title": self._page_title,
            "focus": focus,
            "controls": cache.get("controls", []),
            "controlCount": cache.get("controlCount", len(cache.get("controls", []))),
            "controlsTruncated": cache.get("controlsTruncated", False),
            "pageContentVisible": self._page_content_visible is not False,
            "accessibilityTreeNodeCount": cache.get("treeNodeCount"),
            "successMatched": False,
            "lifecycle": self._lifecycle(page_url, self._dom_dialog_open),
        }

    def _mark_page_monitor_unavailable(self) -> None:
        self._page_monitor_active = False
        self._native_dialog_open = None
        if self._dom_dialog_open is not True:
            self._dom_dialog_open = None
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
        script_execution_disabled = False
        animation_playback_paused = False
        try:
            # Keep the DOM and layout stable from geometry collection through
            # capture; uploaded page scripts cannot move controls between them.
            self.connection.call("Animation.enable")
            self.connection.call("Animation.setPlaybackRate", {"playbackRate": 0})
            animation_playback_paused = True
            self.connection.call(
                "Emulation.setScriptExecutionDisabled", {"value": True}
            )
            script_execution_disabled = True

            frame_tree_result = self.connection.call("Page.getFrameTree")
            frame_tree = (
                frame_tree_result.get("frameTree")
                if isinstance(frame_tree_result, dict)
                else None
            )
            main_frame = frame_tree.get("frame") if isinstance(frame_tree, dict) else None
            child_frames = (
                frame_tree.get("childFrames", [])
                if isinstance(frame_tree, dict)
                else None
            )
            if (
                not isinstance(main_frame, dict)
                or not isinstance(main_frame.get("id"), str)
                or not isinstance(child_frames, list)
                or child_frames
            ):
                raise BrowserError("screenshot redaction cannot safely cover nested frames")

            self.connection.call("DOM.enable")
            self.connection.call("CSS.enable")
            document_result = self.connection.call(
                "DOM.getDocument", {"depth": -1, "pierce": True}
            )
            root = document_result.get("root") if isinstance(document_result, dict) else None
            if not isinstance(root, dict):
                raise BrowserError("browser returned no DOM for screenshot redaction")
            bounds = self._editable_bounds_from_dom(root)

            screenshot_result = self.connection.call(
                "Page.captureScreenshot", {"format": "png"}
            )
            encoded = (
                screenshot_result.get("data")
                if isinstance(screenshot_result, dict)
                else None
            )
            if not isinstance(encoded, str):
                raise BrowserError("browser returned no screenshot")
            try:
                screenshot = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as error:
                raise BrowserError("browser returned an invalid screenshot") from error
            redacted = _redact_png(screenshot, bounds)
            return redacted
        finally:
            restore_error = None
            if script_execution_disabled:
                try:
                    self.connection.call(
                        "Emulation.setScriptExecutionDisabled", {"value": False}
                    )
                except BrowserError as error:
                    restore_error = error
            if animation_playback_paused:
                try:
                    self.connection.call(
                        "Animation.setPlaybackRate", {"playbackRate": 1}
                    )
                except BrowserError as error:
                    restore_error = restore_error or error
            if restore_error is not None:
                raise BrowserError("browser could not restore page execution after screenshot") from restore_error

    def _editable_bounds_from_dom(self, root: Dict[str, Any]) -> list:
        """Collect geometry through CDP, including controls in shadow roots."""
        editable_nodes = []
        pending = [(root, ())]
        visited = set()
        computed_style_cache = {}
        while pending:
            node, ancestor_ids = pending.pop()
            if not isinstance(node, dict):
                raise BrowserError("browser returned an invalid DOM node")
            backend_node_id = node.get("backendNodeId")
            if backend_node_id is not None:
                if not isinstance(backend_node_id, int) or isinstance(backend_node_id, bool):
                    raise BrowserError("browser returned an invalid DOM backend id")
                if backend_node_id in visited:
                    continue
                visited.add(backend_node_id)

            node_name = node.get("nodeName")
            if isinstance(node_name, str) and node_name.startswith("#"):
                normalized_name = node_name.upper()
            elif isinstance(node_name, str):
                normalized_name = node_name.upper()
            else:
                raise BrowserError("browser returned a DOM node without a name")

            attributes = node.get("attributes", [])
            if not isinstance(attributes, list) or len(attributes) % 2:
                raise BrowserError("browser returned invalid DOM attributes")
            if not all(isinstance(value, str) for value in attributes):
                raise BrowserError("browser returned invalid DOM attributes")
            attribute_map = {
                attributes[index].lower(): attributes[index + 1]
                for index in range(0, len(attributes), 2)
            }
            is_editable = normalized_name in {"INPUT", "TEXTAREA", "SELECT"}
            if normalized_name == "INPUT" and attribute_map.get("type", "text").lower() == "hidden":
                is_editable = False
            role_tokens = attribute_map.get("role", "").lower().split()
            contenteditable = attribute_map.get("contenteditable")
            is_editable = is_editable or any(
                role in {"textbox", "searchbox", "combobox"}
                for role in role_tokens
            ) or (
                contenteditable is not None
                and contenteditable.lower() in {"", "true", "plaintext-only"}
            )
            if is_editable:
                if backend_node_id is None:
                    raise BrowserError("editable DOM node had no backend id")
                editable_nodes.append((backend_node_id, ancestor_ids))
                if len(editable_nodes) > 256:
                    raise BrowserError("page has too many editable nodes to redact safely")

            # Template contents are inert and not painted, so deliberately omit
            # templateContent nodes from screenshot redaction geometry.
            for child_key in ("children", "shadowRoots"):
                children = node.get(child_key, [])
                if children is None:
                    continue
                if not isinstance(children, list):
                    raise BrowserError("browser returned an invalid DOM subtree")
                next_ancestors = ancestor_ids
                if backend_node_id is not None and not normalized_name.startswith("#"):
                    next_ancestors = ancestor_ids + (backend_node_id,)
                pending.extend((child, next_ancestors) for child in children)
            content_document = node.get("contentDocument")
            if content_document is not None:
                raise BrowserError("screenshot redaction cannot cover frame content")

        bounds = []
        for backend_node_id, ancestor_ids in editable_nodes:
            try:
                box_result = self.connection.call(
                    "DOM.getBoxModel", {"backendNodeId": backend_node_id}
                )
                model = box_result.get("model") if isinstance(box_result, dict) else None
                border = model.get("border") if isinstance(model, dict) else None
                if not isinstance(border, list) or len(border) < 8 or len(border) % 2:
                    raise BrowserError("browser returned no safe editable-node geometry")
                coordinates = [float(value) for value in border]
            except (BrowserError, TypeError, ValueError, OverflowError) as error:
                if self._node_is_hidden(ancestor_ids + (backend_node_id,), computed_style_cache):
                    continue
                raise BrowserError("browser returned no safe editable-node geometry") from error
            if not all(math.isfinite(value) for value in coordinates):
                raise BrowserError("browser returned invalid editable-node geometry")
            left = min(coordinates[0::2])
            top = min(coordinates[1::2])
            right = max(coordinates[0::2])
            bottom = max(coordinates[1::2])
            if right <= left or bottom <= top:
                raise BrowserError("browser returned invalid editable-node geometry")
            bounds.append({"left": left, "top": top, "right": right, "bottom": bottom})
        return bounds

    def _node_is_hidden(self, backend_node_ids, cache) -> bool:
        """Ignore an unrendered control only when CDP confirms hidden styling."""
        for backend_node_id in backend_node_ids:
            if backend_node_id not in cache:
                node_result = self.connection.call(
                    "DOM.pushNodesByBackendIdsToFrontend",
                    {"backendNodeIds": [backend_node_id]},
                )
                node_ids = node_result.get("nodeIds") if isinstance(node_result, dict) else None
                node_id = node_ids[0] if isinstance(node_ids, list) and len(node_ids) == 1 else None
                if not isinstance(node_id, int) or isinstance(node_id, bool) or node_id <= 0:
                    raise BrowserError("browser could not resolve a hidden control node")
                result = self.connection.call(
                    "CSS.getComputedStyleForNode", {"nodeId": node_id}
                )
                styles = result.get("computedStyle") if isinstance(result, dict) else None
                if not isinstance(styles, list):
                    raise BrowserError("browser returned no computed style for hidden control")
                cache[backend_node_id] = {
                    item.get("name"): item.get("value")
                    for item in styles
                    if isinstance(item, dict)
                    and isinstance(item.get("name"), str)
                    and isinstance(item.get("value"), str)
                }
            style = cache[backend_node_id]
            if (
                style.get("display") == "none"
                or style.get("visibility") in {"hidden", "collapse"}
                or style.get("content-visibility") == "hidden"
            ):
                return True
            try:
                if float(style.get("opacity", "1")) == 0:
                    return True
            except (TypeError, ValueError, OverflowError):
                pass
        return False

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
        lifecycle = self._lifecycle(current_url, self._dom_dialog_open)
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
            try:
                profile_process_ids = _process_ids_using_profile(
                    self.profile_directory
                )
            except BrowserCleanupError as error:
                cleanup_errors.append(error)
                profile_process_ids = set()
            process_ids = (
                _descendant_process_ids(process.pid)
                | profile_process_ids
                | {process.pid}
            )
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
