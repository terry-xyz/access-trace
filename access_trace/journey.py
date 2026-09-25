"""The fixed contact-form keyboard journey and redacted evidence lifecycle."""

import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from .browser import (
    BrowserActionError,
    BrowserCleanupError,
    BrowserError,
    IsolatedKeyboardBrowser,
)
from .domain import DEMO_TITLE, LOOPBACK_HOSTS, SUPPORTED_GOAL, utc_now
from .planner import CodexPlanner, PlannerError, validate_action


MAX_INTERACTIONS = 16
BROWSER_RUN_LOCK = threading.Lock()


MAX_PAGE_STRING_LENGTH = 80
MAX_CHARACTER_COUNT = 100_000
MAX_CONTROLS = 8


def _bounded_page_string(value: Any, limit: int = MAX_PAGE_STRING_LENGTH) -> Optional[str]:
    if not isinstance(value, str):
        return None
    return value[:limit]


def _bounded_character_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(count, MAX_CHARACTER_COUNT))


def _focus_snapshot(observation: Dict[str, Any]) -> Dict[str, Any]:
    focus = observation.get("focus", {})
    if not isinstance(focus, dict):
        focus = {}
    return {
        "role": _bounded_page_string(focus.get("role")),
        "accessibleName": _bounded_page_string(focus.get("accessibleName")),
        "tag": _bounded_page_string(focus.get("tag")),
        "stableId": _bounded_page_string(focus.get("stableId")),
        "isStable": bool(focus.get("isStable")),
        "characterCount": _bounded_character_count(focus.get("characterCount", 0)),
        "acceptedInput": bool(focus.get("acceptedInput")),
        "validationState": _bounded_page_string(
            focus.get("validationState", "not-observed")
        ),
    }


def _goal_progress(observation: Dict[str, Any]) -> Dict[str, Any]:
    controls = observation.get("controls", [])
    if not isinstance(controls, list):
        controls = []
    focus = observation.get("focus", {})
    if not isinstance(focus, dict):
        focus = {}
    fields = {}
    for control in controls:
        if not isinstance(control, dict):
            continue
        stable_id = control.get("stableId")
        if not isinstance(stable_id, str):
            continue
        if stable_id not in {"name", "email", "message"}:
            continue
        fields[stable_id] = {
            "characterCount": _bounded_character_count(
                control.get("characterCount", 0)
            ),
            "acceptedInput": bool(control.get("acceptedInput")),
            "validationState": _bounded_page_string(
                control.get("validationState", "not-observed")
            ),
        }
    completed_fields = sum(1 for field in fields.values() if field["acceptedInput"])
    success_matched = bool(observation.get("successMatched"))
    return {
        "goal": SUPPORTED_GOAL,
        "status": (
            "completed"
            if success_matched
            else ("in-progress" if completed_fields else "not-started")
        ),
        "completed": success_matched,
        "completedFields": completed_fields,
        "expectedFields": 3,
        "fields": fields,
        "submitFocused": focus.get("stableId") == "submit",
    }


def _redacted_url(raw_url: Any, target_url: str) -> Optional[str]:
    if not isinstance(raw_url, str):
        return None
    try:
        observed = urlsplit(raw_url)
        target = urlsplit(target_url)
        observed_port = observed.port
        target_port = target.port
    except ValueError:
        return None
    same_loopback_origin = (
        observed.hostname in LOOPBACK_HOSTS
        and target.hostname in LOOPBACK_HOSTS
    )
    if (
        observed.scheme != target.scheme
        or not (observed.hostname == target.hostname or same_loopback_origin)
        or observed_port != target_port
    ):
        return None
    return target_url


def _redacted_title(raw_title: Any) -> Optional[str]:
    if raw_title == DEMO_TITLE:
        return DEMO_TITLE
    if isinstance(raw_title, str):
        return "[redacted]"
    return None


def redacted_observation(raw: Dict[str, Any], target_url: str) -> Dict[str, Any]:
    bounded_url = _redacted_url(raw.get("url"), target_url)
    raw_lifecycle = raw.get("lifecycle", {})
    if not isinstance(raw_lifecycle, dict):
        raw_lifecycle = {}
    lifecycle = {
        key: bool(raw_lifecycle.get(key))
        for key in (
            "pageOpen",
            "dialogOpen",
            "popupObserved",
            "crashed",
            "offLoopbackRedirect",
        )
    }
    observation = {
        "kind": "settled-observation",
        "observedAt": utc_now(),
        "url": bounded_url,
        "title": _redacted_title(raw.get("title")),
        "focus": _focus_snapshot(raw),
        "controls": [],
        "warnings": [],
        "lifecycle": lifecycle,
        "success": {
            "condition": "Message sent",
            "matched": bool(raw.get("successMatched")),
        },
        "goalProgress": _goal_progress(raw),
        "coverage": None,
    }
    raw_controls = raw.get("controls", [])
    if not isinstance(raw_controls, list):
        raw_controls = []
    for control in raw_controls[:MAX_CONTROLS]:
        if not isinstance(control, dict):
            continue
        safe_control = {}
        for key in ("role", "accessibleName", "tag", "stableId", "validationState"):
            if key in control:
                safe_control[key] = _bounded_page_string(control[key])
        for key in ("focusable", "isStable", "acceptedInput"):
            if key in control:
                safe_control[key] = bool(control[key])
        if "characterCount" in control:
            safe_control["characterCount"] = _bounded_character_count(
                control["characterCount"]
            )
        safe_control.setdefault("focusable", True)
        observation["controls"].append(safe_control)
    if bounded_url is None:
        observation["warnings"].append({"kind": "off-loopback-redirect"})
        observation["lifecycle"]["offLoopbackRedirect"] = True
    return observation


_redacted_observation = redacted_observation


def _append_action(
    run: Dict[str, Any], action: Dict[str, Any], before: Dict[str, Any], status: str
) -> None:
    sequence = len(run["actions"]) + 1
    if action["kind"] == "key":
        record = {
            "sequence": sequence,
            "kind": "key",
            "key": action["key"],
            "allowed": True,
            "status": status,
            "focusBefore": _focus_snapshot(before),
            "actedAt": utc_now(),
        }
    else:
        record = {
            "sequence": sequence,
            "kind": "type",
            "field": action["field"],
            "characterCount": len(action["value"]),
            "retained": False,
            "allowed": True,
            "status": status,
            "focusBefore": _focus_snapshot(before),
            "actedAt": utc_now(),
        }
    run["actions"].append(record)


def _set_terminal_state(
    run: Dict[str, Any], status: str, observation: Dict[str, Any], started: float
) -> None:
    now = utc_now()
    run["status"] = status
    run["updatedAt"] = now
    run["completedAt"] = now
    run["durationMs"] = max(1, int((time.monotonic() - started) * 1000))
    run["interactionCount"] = len(run["actions"])
    run["stoppingPoint"] = {
        "focus": observation["focus"],
        "successCondition": observation["success"]["condition"],
        "successMatched": observation["success"]["matched"],
        "goalProgress": observation["goalProgress"],
        "observedAt": observation["observedAt"],
    }


def _submit_activation_observed(run: Dict[str, Any]) -> bool:
    if not run.get("actions"):
        return False
    action = run["actions"][-1]
    focus = action.get("focusBefore", {})
    return (
        action.get("kind") == "key"
        and action.get("key") == "Enter"
        and focus.get("role") == "button"
        and focus.get("accessibleName") == "Submit"
    )


def _complete_if_verified(
    run: Dict[str, Any],
    observation: Dict[str, Any],
    started: float,
    browser: IsolatedKeyboardBrowser,
    evidence_directory: Optional[Path],
) -> bool:
    if not observation["success"]["matched"] or not _submit_activation_observed(run):
        return False
    if evidence_directory is None:
        raise BrowserError("completed evidence requires a screenshot directory")
    destination = evidence_directory / (run["id"] + "-stopping.png")
    try:
        screenshot_ref = browser.capture_redacted_screenshot(destination)
    except OSError as error:
        raise BrowserError("browser did not persist a redacted PNG screenshot") from error
    if not isinstance(screenshot_ref, str) or screenshot_ref != destination.name:
        raise BrowserError("browser returned an invalid screenshot reference")
    try:
        screenshot_path = (evidence_directory / screenshot_ref).resolve()
        screenshot_path.relative_to(evidence_directory.resolve())
        with screenshot_path.open("rb") as screenshot_file:
            if screenshot_file.read(8) != b"\x89PNG\r\n\x1a\n":
                raise BrowserError("browser did not persist a redacted PNG screenshot")
    except (OSError, ValueError) as error:
        raise BrowserError("browser did not persist a redacted PNG screenshot") from error
    run["stoppingScreenshotRef"] = screenshot_ref
    _set_terminal_state(run, "COMPLETED", observation, started)
    return True


def execute_fixed_goal(
    run: Dict[str, Any],
    evidence_directory: Optional[Path] = None,
    planner: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute one fixed-goal run and return the durable, redacted record."""
    with BROWSER_RUN_LOCK:
        return _execute_fixed_goal(run, evidence_directory, planner)


def _execute_fixed_goal(
    run: Dict[str, Any], evidence_directory: Optional[Path], planner: Optional[Any]
) -> Dict[str, Any]:
    if run.get("goal") != SUPPORTED_GOAL or run.get("targetVersion") != "fixed":
        raise ValueError("this lifecycle only supports the fixed contact-form goal")
    started = time.monotonic()
    run["startedAt"] = utc_now()
    run["browserSession"]["isolation"] = "fresh"
    run["browserSession"]["startedAt"] = run["startedAt"]
    run["agentFailure"] = None
    run["browserFailure"] = None
    if evidence_directory is None:
        run["warnings"].append({"kind": "missing-evidence-directory"})
        run["browserSession"]["cleanup"] = {
            "status": "not-started",
            "profileRemoved": True,
        }
        _set_terminal_state(run, "INCONCLUSIVE", run["observations"][0], started)
        return run
    planner = planner or CodexPlanner()
    browser: Optional[IsolatedKeyboardBrowser] = None
    try:
        browser = IsolatedKeyboardBrowser(run["targetUrl"])
        current_raw = browser.observe()
        current = _redacted_observation(current_raw, run["targetUrl"])
        run["observations"] = [current]

        for _ in range(MAX_INTERACTIONS):
            bounded_for_planner = {
                "goal": run["goal"],
                "successCondition": run["successCondition"],
                "simulationMode": run["simulationMode"],
                "interactionProfile": run["interactionProfile"],
                "pageEvidence": {
                    "untrusted": True,
                    "url": current["url"],
                    "title": current["title"],
                    "focus": current["focus"],
                    "controls": current["controls"],
                    "successMatched": current["success"]["matched"],
                },
                "goalProgress": current["goalProgress"],
                "warnings": current["warnings"],
                "recentHistory": [
                    {
                        "kind": action["kind"],
                        "key": action.get("key"),
                        "field": action.get("field"),
                        "characterCount": action.get("characterCount"),
                    }
                    for action in run["actions"][-4:]
                ],
            }
            action = validate_action(
                planner.next_action(bounded_for_planner), bounded_for_planner
            )
            if action["kind"] == "complete":
                if _complete_if_verified(
                    run, current, started, browser, evidence_directory
                ):
                    return run
                raise BrowserError("planner stopped without locally verified success")
            before = current
            try:
                if action["kind"] == "key":
                    browser.press_key(action["key"])
                else:
                    browser.type_text(action["value"])
            except BrowserActionError:
                _append_action(run, action, before, "failed")
                try:
                    current = _redacted_observation(
                        browser.observe(), run["targetUrl"]
                    )
                    run["observations"].append(current)
                except BrowserError:
                    pass
                raise
            _append_action(run, action, before, "delivered")
            current = _redacted_observation(browser.observe(), run["targetUrl"])
            run["observations"].append(current)
            if current["lifecycle"].get("offLoopbackRedirect"):
                raise BrowserError("browser left the controlled local target")
            if _complete_if_verified(
                run, current, started, browser, evidence_directory
            ):
                return run

        raise BrowserError("keyboard journey exceeded its bounded interaction limit")
    except PlannerError as error:
        run["warnings"].append({"kind": "planner-failure", "message": str(error)})
        run["agentFailure"] = {"kind": "planner-failure"}
        fallback = run["observations"][-1]
        _set_terminal_state(run, "INCONCLUSIVE", fallback, started)
        return run
    except (BrowserError, BrowserActionError) as error:
        run["warnings"].append({"kind": "browser-failure", "message": str(error)})
        run["agentFailure"] = {"kind": "browser-failure"}
        if isinstance(error, BrowserCleanupError):
            run["browserFailure"] = {"kind": "cleanup-failure"}
            run["browserSession"]["cleanup"] = {
                "status": "failed",
                "profileRemoved": False,
            }
        fallback = run["observations"][-1] if run.get("observations") else {
            "focus": {},
            "success": {"condition": "Message sent", "matched": False},
            "goalProgress": {},
            "observedAt": utc_now(),
        }
        _set_terminal_state(run, "INCONCLUSIVE", fallback, started)
        return run
    finally:
        if browser is not None:
            try:
                browser.close()
            except BrowserError:
                run["warnings"].append({"kind": "browser-cleanup-failure"})
                run["browserFailure"] = {"kind": "cleanup-failure"}
                run["browserSession"]["cleanup"] = {
                    "status": "failed",
                    "profileRemoved": False,
                }
                if run.get("status") == "COMPLETED":
                    _set_terminal_state(
                        run, "INCONCLUSIVE", run["observations"][-1], started
                    )
            else:
                run["browserSession"]["cleanup"] = {
                    "status": "verified",
                    "profileRemoved": True,
                }
        run["browserSession"]["closedAt"] = utc_now()
        run["updatedAt"] = utc_now()
