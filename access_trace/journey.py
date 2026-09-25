"""The contact-form keyboard journeys and redacted evidence lifecycle."""

import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

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


MAX_PAGE_URL_LENGTH = 256
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


def _redacted_url(
    raw_url: Any, target_url: str, sensitive_values: Iterable[str]
) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(raw_url, str):
        return None, "off-loopback-redirect"
    try:
        observed = urlsplit(raw_url[:4096])
        target = urlsplit(target_url)
        observed_port = observed.port
        target_port = target.port
    except ValueError:
        return None, "off-loopback-redirect"
    same_loopback_origin = (
        observed.hostname in LOOPBACK_HOSTS
        and target.hostname in LOOPBACK_HOSTS
    )
    if (
        observed.scheme != target.scheme
        or not (observed.hostname == target.hostname or same_loopback_origin)
        or observed_port != target_port
    ):
        return None, "off-loopback-redirect"
    if observed.hostname is None:
        return None, "off-loopback-redirect"
    safe_host = observed.hostname
    if ":" in safe_host:
        safe_host = "[" + safe_host + "]"
    safe_netloc = safe_host
    if observed_port is not None:
        safe_netloc += ":" + str(observed_port)
    original_path = observed.path or "/"
    observed_path = original_path[:MAX_PAGE_URL_LENGTH]
    decoded_path = unquote(original_path[:MAX_PAGE_URL_LENGTH])
    if any(
        isinstance(value, str) and value and (value in observed_path or value in decoded_path)
        for value in sensitive_values
    ):
        observed_path = "/[redacted-path]"
    safe_url = urlunsplit(
        (observed.scheme, safe_netloc, observed_path, "", "")
    )
    safe_url = safe_url[:MAX_PAGE_URL_LENGTH]
    navigation_warning = (
        "navigation-redirect"
        if original_path != (target.path or "/")
        else None
    )
    return safe_url, navigation_warning


def _redacted_title(raw_title: Any) -> Optional[str]:
    if raw_title == DEMO_TITLE:
        return DEMO_TITLE
    if isinstance(raw_title, str):
        return "[redacted]"
    return None


def redacted_observation(
    raw: Dict[str, Any],
    target_url: str,
    sensitive_values: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    bounded_url, navigation_warning = _redacted_url(
        raw.get("url"), target_url, sensitive_values or ()
    )
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
            "navigationRedirect",
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
    elif navigation_warning is not None:
        observation["warnings"].append({"kind": navigation_warning})
        observation["lifecycle"]["navigationRedirect"] = True
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
            "characterCount": len(action["text"]),
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


def _is_submit_focus(observation: Dict[str, Any]) -> bool:
    focus = observation.get("focus", {})
    return (
        isinstance(focus, dict)
        and focus.get("role") == "button"
        and focus.get("accessibleName") == "Submit"
    )


def _is_submit_focus_snapshot(focus: Dict[str, Any]) -> bool:
    return _is_submit_focus({"focus": focus})


def _same_submit_focus(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    if not _is_submit_focus(left) or not _is_submit_focus(right):
        return False
    return _focus_snapshot(left) == _focus_snapshot(right)


def _unchanged_goal_progress(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return left.get("goalProgress") == right.get("goalProgress")


def _has_relevant_overlay(observation: Dict[str, Any]) -> bool:
    lifecycle = observation.get("lifecycle", {})
    return isinstance(lifecycle, dict) and bool(
        lifecycle.get("dialogOpen") or lifecycle.get("popupObserved")
    )


def _persist_stopping_screenshot(
    run: Dict[str, Any], browser: IsolatedKeyboardBrowser, evidence_directory: Optional[Path]
) -> None:
    if evidence_directory is None:
        raise BrowserError("terminal evidence requires a screenshot directory")
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


def _settle_action(
    run: Dict[str, Any],
    browser: IsolatedKeyboardBrowser,
    action: Dict[str, Any],
    before: Dict[str, Any],
    typed_values: Dict[str, str],
) -> Dict[str, Any]:
    try:
        if action["kind"] == "key":
            browser.press_key(action["key"])
        else:
            browser.type_text(action["text"])
            typed_values[action["field"]] = action["text"]
    except BrowserActionError:
        _append_action(run, action, before, "failed")
        try:
            current = _redacted_observation(
                browser.observe(), run["targetUrl"], typed_values.values()
            )
            run["observations"].append(current)
        except BrowserError:
            pass
        raise
    _append_action(run, action, before, "delivered")
    current = _redacted_observation(
        browser.observe(), run["targetUrl"], typed_values.values()
    )
    run["observations"].append(current)
    if current["lifecycle"].get("offLoopbackRedirect") or current["lifecycle"].get(
        "navigationRedirect"
    ):
        raise BrowserError("browser navigated away from the controlled target")
    return current


def _record_recovery_step(
    recovery_actions: list, action: Dict[str, Any], before: Dict[str, Any], after: Dict[str, Any]
) -> None:
    recovery_actions.append(
        {
            "key": action["key"],
            "status": "delivered",
            "focusBefore": _focus_snapshot(before),
            "focusAfter": _focus_snapshot(after),
        }
    )


def _dismiss_relevant_overlay(
    run: Dict[str, Any],
    browser: IsolatedKeyboardBrowser,
    current: Dict[str, Any],
    typed_values: Dict[str, str],
    recovery_actions: list,
) -> Tuple[Dict[str, Any], bool]:
    if not _has_relevant_overlay(current):
        return current, False
    after = _settle_action(
        run,
        browser,
        {"kind": "key", "key": "Escape"},
        current,
        typed_values,
    )
    _record_recovery_step(
        recovery_actions,
        {"kind": "key", "key": "Escape"},
        current,
        after,
    )
    return after, True


def _local_submit_recovery(
    initial_submit: Dict[str, Any], recovery_actions: list
) -> bool:
    navigation = [
        step
        for step in recovery_actions
        if step.get("key") in {"Shift+Tab", "Tab"}
    ]
    if len(navigation) != 2 or [step["key"] for step in navigation] != [
        "Shift+Tab",
        "Tab",
    ]:
        return False
    controls = initial_submit.get("controls", [])
    if not isinstance(controls, list):
        return False
    control_ids = [
        control.get("stableId")
        for control in controls
        if isinstance(control, dict) and control.get("stableId")
    ]
    try:
        submit_index = control_ids.index("submit")
    except ValueError:
        return False
    if submit_index == 0:
        return False
    previous_id = control_ids[submit_index - 1]
    return (
        navigation[0]["focusAfter"].get("stableId") == previous_id
        and _is_submit_focus_snapshot(navigation[1]["focusAfter"])
    )


def _classify_broken_barrier(
    run: Dict[str, Any],
    browser: IsolatedKeyboardBrowser,
    initial_submit: Dict[str, Any],
    started: float,
    evidence_directory: Optional[Path],
    typed_values: Dict[str, str],
) -> Tuple[str, Dict[str, Any]]:
    """Probe a semantic Submit stopping point before calling it a barrier."""
    activation_actions = []
    recovery_actions = []
    overlay_seen = False
    current = initial_submit

    current, dismissed_overlay = _dismiss_relevant_overlay(
        run, browser, current, typed_values, recovery_actions
    )
    overlay_seen = dismissed_overlay

    for key in ("Enter", "Space"):
        before = current
        current = _settle_action(
            run, browser, {"kind": "key", "key": key}, before, typed_values
        )
        activation_actions.append(key)
        if current["success"]["matched"]:
            if _complete_if_verified(
                run, current, started, browser, evidence_directory
            ):
                return "completed", current
            return "inconclusive", current
        current, dismissed_overlay = _dismiss_relevant_overlay(
            run, browser, current, typed_values, recovery_actions
        )
        overlay_seen = overlay_seen or dismissed_overlay
        if not _same_submit_focus(initial_submit, current) or not _unchanged_goal_progress(
            initial_submit, current
        ):
            break

    for key in ("Shift+Tab", "Tab"):
        after = _settle_action(
            run,
            browser,
            {"kind": "key", "key": key},
            current,
            typed_values,
        )
        _record_recovery_step(
            recovery_actions,
            {"kind": "key", "key": key},
            current,
            after,
        )
        current = after

    unchanged_progress = _unchanged_goal_progress(initial_submit, current)
    same_submit_focus = _same_submit_focus(initial_submit, current)
    local_focus_recovery = _local_submit_recovery(initial_submit, recovery_actions)
    whole_page_wrapped = not local_focus_recovery
    recovery_record = {
        "kind": "submit-barrier-recovery",
        "attemptedActivations": activation_actions,
        "actions": recovery_actions,
        "initialFocus": _focus_snapshot(initial_submit),
        "finalFocus": _focus_snapshot(current),
        "unchangedProgress": unchanged_progress,
        "sameSubmitFocus": same_submit_focus,
        "localFocusRecovery": local_focus_recovery,
        "wholePageWrapped": whole_page_wrapped,
        "successMatched": bool(current["success"]["matched"]),
    }
    run.setdefault("recoveryEvidence", []).append(recovery_record)

    if (
        len(activation_actions) == 2
        and activation_actions == ["Enter", "Space"]
        and not overlay_seen
        and not whole_page_wrapped
        and not current["success"]["matched"]
        and unchanged_progress
        and same_submit_focus
    ):
        _persist_stopping_screenshot(run, browser, evidence_directory)
        _set_terminal_state(run, "BLOCKED", current, started)
        return "blocked", current

    run["warnings"].append({"kind": "barrier-evidence-inconclusive"})
    _set_terminal_state(run, "INCONCLUSIVE", current, started)
    return "inconclusive", current


def _submit_activation_observed(run: Dict[str, Any]) -> bool:
    if not run.get("actions"):
        return False
    action = run["actions"][-1]
    focus = action.get("focusBefore", {})
    return (
        action.get("kind") == "key"
        and action.get("key") in {"Enter", "Space"}
        and _is_submit_focus_snapshot(focus)
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
    _persist_stopping_screenshot(run, browser, evidence_directory)
    _set_terminal_state(run, "COMPLETED", observation, started)
    return True


def execute_contact_goal(
    run: Dict[str, Any],
    evidence_directory: Optional[Path] = None,
    planner: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute the supported fixed or broken contact-form goal."""
    with BROWSER_RUN_LOCK:
        return _execute_contact_goal(run, evidence_directory, planner)


def execute_fixed_goal(
    run: Dict[str, Any],
    evidence_directory: Optional[Path] = None,
    planner: Optional[Any] = None,
) -> Dict[str, Any]:
    """Backward-compatible public entry point for the fixed contact form."""
    if run.get("targetVersion") != "fixed":
        raise ValueError("this lifecycle only supports the fixed contact-form goal")
    return execute_contact_goal(run, evidence_directory, planner)


def _execute_contact_goal(
    run: Dict[str, Any], evidence_directory: Optional[Path], planner: Optional[Any]
) -> Dict[str, Any]:
    if run.get("goal") != SUPPORTED_GOAL or run.get("targetVersion") not in {
        "fixed",
        "broken",
    }:
        raise ValueError("this lifecycle only supports the fixed or broken contact-form goal")
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
    typed_values: Dict[str, str] = {}
    try:
        browser = IsolatedKeyboardBrowser(run["targetUrl"])
        current_raw = browser.observe()
        current = _redacted_observation(
            current_raw, run["targetUrl"], typed_values.values()
        )
        run["observations"] = [current]
        if current["lifecycle"].get("offLoopbackRedirect") or current["lifecycle"].get(
            "navigationRedirect"
        ):
            raise BrowserError("browser navigated away from the controlled target")

        for _ in range(MAX_INTERACTIONS):
            if run.get("targetVersion") == "broken" and _is_submit_focus(current):
                barrier_status, current = _classify_broken_barrier(
                    run,
                    browser,
                    current,
                    started,
                    evidence_directory,
                    typed_values,
                )
                if barrier_status in {"blocked", "completed", "inconclusive"}:
                    return run

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
            current = _settle_action(run, browser, action, current, typed_values)
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
                if run.get("status") in {"COMPLETED", "BLOCKED"}:
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
