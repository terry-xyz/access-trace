"""The contact-form keyboard journeys and redacted evidence lifecycle."""

import copy
from contextlib import nullcontext
from contextvars import ContextVar
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

from .browser import (
    BrowserActionError,
    BrowserCleanupError,
    BrowserError,
    IsolatedKeyboardBrowser,
    MAX_PLANNER_SCREENSHOT_BYTES,
)
from .domain import DEMO_TITLE, LOOPBACK_HOSTS, SUPPORTED_GOAL, utc_now
from .evidence import attach_evidence_handoff
from .planner import CodexPlanner, PlannerError, validate_action
from .url_policy import is_browser_error_url, same_web_origin


BROWSER_RUN_LOCK = threading.Lock()
_TERMINAL_COORDINATION = ContextVar(
    "access_trace_terminal_coordination", default=None
)


MAX_PAGE_URL_LENGTH = 256
MAX_PAGE_STRING_LENGTH = 80
MAX_CHARACTER_COUNT = 100_000
MAX_CONTROLS = 8
LIFECYCLE_FIELDS = (
    "pageOpen",
    "dialogOpen",
    "dialogObserved",
    "popupObserved",
    "crashed",
    "offLoopbackRedirect",
    "navigationRedirect",
)
MISSING_LIFECYCLE = object()


class ActionDeliveryFailure(BrowserActionError):
    """A permitted action was not delivered, with a fresh observation attached."""

    def __init__(
        self,
        message: str,
        observation: Optional[Dict[str, Any]] = None,
        attempts: int = 1,
    ):
        super().__init__(message)
        self.observation = observation
        self.attempts = attempts


def _append_warning(target: list, warning: Dict[str, Any]) -> None:
    if warning not in target:
        target.append(warning)


def _lifecycle_warnings(raw_lifecycle: Dict[str, Any]) -> list:
    warnings = []
    if raw_lifecycle.get("headfulFallback"):
        warnings.append({
            "kind": "headful-browser-fallback",
            "message": "Headless Chrome exposed an empty page, so the assessment retried once in a separate isolated Chrome session.",
        })
    if raw_lifecycle.get("pageContentVisible") is False:
        warnings.append({
            "kind": "page-content-unavailable",
            "message": "The selected URL loaded, but the isolated browser exposed no visible text, focusable controls, or media.",
        })
    if raw_lifecycle.get("wwwHostFallback"):
        warnings.append({
            "kind": "www-host-fallback",
            "message": "The submitted hostname did not resolve; assessment continued on its www hostname.",
        })
    if raw_lifecycle.get("browserLoadError"):
        warnings.append({
            "kind": "page-load-failed",
            "message": "The browser displayed a network error page instead of loading the selected website.",
        })
    if raw_lifecycle.get("dialogOpen"):
        warnings.append({"kind": "dialog-open"})
    if raw_lifecycle.get("dialogObserved"):
        warnings.append({"kind": "dialog-observed"})
    if raw_lifecycle.get("popupObserved"):
        warnings.append({"kind": "popup-observed"})
    if raw_lifecycle.get("popupAttempted"):
        warnings.append({"kind": "popup-attempted"})
    if raw_lifecycle.get("crashed"):
        warnings.append({"kind": "browser-crashed"})
    if raw_lifecycle.get("pageOpen") is False:
        warnings.append({"kind": "page-closed"})
    if raw_lifecycle.get("offLoopbackRedirect"):
        warnings.append({"kind": "off-loopback-redirect"})
    if raw_lifecycle.get("navigationRedirect"):
        warnings.append({"kind": "navigation-redirect"})
    return warnings


def _record_observation_warnings(run: Dict[str, Any], observation: Dict[str, Any]) -> None:
    for warning in observation.get("warnings", []):
        if isinstance(warning, dict):
            _append_warning(run["warnings"], warning)


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


def _optional_bool(value: Any) -> Optional[bool]:
    return None if value is None else bool(value)


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
        "acceptedInput": _optional_bool(focus.get("acceptedInput")),
        "validationState": _bounded_page_string(
            focus.get("validationState", "not-observed")
        ),
    }


def _goal_progress(
    observation: Dict[str, Any],
    goal: Optional[str] = SUPPORTED_GOAL,
    success_condition: Optional[str] = "Message sent",
) -> Optional[Dict[str, Any]]:
    if goal is None:
        return None
    if goal != SUPPORTED_GOAL:
        return {
            "goal": goal,
            "status": "not-started",
            "completed": False,
            "support": "agent-evaluates",
        }
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
            "acceptedInput": _optional_bool(control.get("acceptedInput")),
            "validationState": _bounded_page_string(
                control.get("validationState", "not-observed")
            ),
        }
    completed_fields = sum(1 for field in fields.values() if field["acceptedInput"])
    success_matched = (
        success_condition == "Message sent"
        and bool(observation.get("successMatched"))
    )
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


def _agent_goal_progress(
    goal: str, status: str, reason: Optional[str] = None
) -> Dict[str, Any]:
    progress = {
        "goal": goal,
        "status": status,
        "completed": status == "completed",
        "support": "agent-evaluates",
    }
    if isinstance(reason, str) and reason.strip():
        progress["reason"] = reason.strip()[:240]
    return progress


def _coverage_progress(
    raw: Dict[str, Any], covered_focus_ids: Optional[set] = None
) -> Dict[str, Any]:
    covered_focus_ids = covered_focus_ids if covered_focus_ids is not None else set()
    raw_lifecycle = raw.get("lifecycle", {})
    if not isinstance(raw_lifecycle, dict):
        raw_lifecycle = {}
    page_observed = (
        bool(raw_lifecycle.get("pageOpen"))
        and isinstance(raw.get("url"), str)
        and raw_lifecycle.get("pageContentVisible") is not False
    )
    focus = raw.get("focus", {})
    if isinstance(focus, dict):
        focused_id = focus.get("stableId")
        if (
            isinstance(focused_id, str)
            and focused_id
            and focused_id != "document"
            and bool(focus.get("isStable"))
        ):
            covered_focus_ids.add(focused_id)

    controls = raw.get("controls", [])
    if not isinstance(controls, list):
        controls = []
    expected_focus_ids = sorted(
        {
            control.get("stableId")
            for control in controls
            if isinstance(control, dict)
            and control.get("focusable", True)
            and isinstance(control.get("stableId"), str)
            and control.get("stableId")
            and control.get("isStable", True)
        }
    )
    control_count = raw.get("controlCount")
    if not isinstance(control_count, int) or isinstance(control_count, bool):
        control_count = len(expected_focus_ids)
    control_count = max(0, control_count)
    visited_focus_ids = sorted(set(expected_focus_ids).intersection(covered_focus_ids))
    visited_count = min(control_count, len(covered_focus_ids))
    complete = page_observed and visited_count >= control_count
    score_percentage = (
        round((visited_count / control_count) * 100)
        if control_count > 0 and page_observed
        else None
    )
    return {
        "status": (
            "completed"
            if complete
            else ("in-progress" if page_observed else "not-started")
        ),
        "completed": complete,
        "areasObserved": 1 if page_observed else 0,
        "areasExpected": 1,
        "controlsObserved": visited_count,
        "controlsExpected": control_count,
        "scorePercentage": score_percentage,
        "visitedControls": visited_focus_ids,
        "expectedControls": expected_focus_ids,
        "controlsTruncated": bool(raw.get("controlsTruncated")),
    }


def _redacted_url(
    raw_url: Any, target_url: str, sensitive_values: Iterable[str]
) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(raw_url, str):
        return None, None
    if is_browser_error_url(raw_url):
        return None, None
    try:
        observed = urlsplit(raw_url[:4096])
        target = urlsplit(target_url)
        observed_port = observed.port or (443 if observed.scheme == "https" else 80)
        target_port = target.port or (443 if target.scheme == "https" else 80)
    except ValueError:
        return None, "navigation-redirect"
    if observed.hostname is None:
        return None, "navigation-redirect"
    target_is_loopback = target.hostname in LOOPBACK_HOSTS
    observed_is_loopback = observed.hostname in LOOPBACK_HOSTS
    same_target_origin = (
        (
            target_is_loopback
            and observed_is_loopback
            and observed.scheme == target.scheme
            and observed_port == target_port
        )
        or (
            not target_is_loopback
            and observed_port in {80, 443}
            and target_port in {80, 443}
            and same_web_origin(target, observed)
        )
    )
    if not same_target_origin:
        return None, "off-loopback-redirect"
    if target_is_loopback and not observed_is_loopback:
        return None, "navigation-redirect"
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
        if target_is_loopback and original_path != (target.path or "/")
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
    assessment_scope: str = "goal-focused",
    goal: Optional[str] = SUPPORTED_GOAL,
    covered_focus_ids: Optional[set] = None,
    success_condition: Optional[str] = "Message sent",
) -> Dict[str, Any]:
    bounded_url, navigation_warning = _redacted_url(
        raw.get("url"), target_url, sensitive_values or ()
    )
    raw_lifecycle_value = raw.get("lifecycle", MISSING_LIFECYCLE)
    if raw_lifecycle_value is MISSING_LIFECYCLE:
        lifecycle_evidence = "missing"
        raw_lifecycle = {}
    elif not isinstance(raw_lifecycle_value, dict):
        lifecycle_evidence = "invalid"
        raw_lifecycle = {}
    elif any(field not in raw_lifecycle_value for field in LIFECYCLE_FIELDS):
        lifecycle_evidence = "incomplete"
        raw_lifecycle = raw_lifecycle_value
    elif any(
        raw_lifecycle_value[field] is not None
        and not isinstance(raw_lifecycle_value[field], bool)
        for field in LIFECYCLE_FIELDS
    ):
        lifecycle_evidence = "invalid"
        raw_lifecycle = raw_lifecycle_value
    elif any(raw_lifecycle_value[field] is None for field in LIFECYCLE_FIELDS):
        lifecycle_evidence = "incomplete"
        raw_lifecycle = raw_lifecycle_value
    else:
        lifecycle_evidence = "observed"
        raw_lifecycle = raw_lifecycle_value
    for field in ("popupAttempted",):
        if field not in raw_lifecycle:
            continue
        value = raw_lifecycle[field]
        if value is not None and not isinstance(value, bool):
            lifecycle_evidence = "invalid"
        elif value is None and lifecycle_evidence == "observed":
            lifecycle_evidence = "incomplete"
    if raw_lifecycle.get("browserLoadError") is True:
        bounded_url = None
        navigation_warning = None
    lifecycle = {
        key: raw_lifecycle.get(key)
        for key in LIFECYCLE_FIELDS + ("popupAttempted",)
    }
    lifecycle["browserLoadError"] = raw_lifecycle.get("browserLoadError")
    lifecycle["wwwHostFallback"] = raw_lifecycle.get("wwwHostFallback")
    lifecycle["pageContentVisible"] = raw_lifecycle.get("pageContentVisible")
    lifecycle["headfulFallback"] = raw_lifecycle.get("headfulFallback")
    for key, value in lifecycle.items():
        if value is not None and not isinstance(value, bool):
            lifecycle[key] = None
    lifecycle["evidence"] = lifecycle_evidence
    is_whole_site = assessment_scope == "whole-site"
    observation = {
        "kind": "settled-observation",
        "observedAt": utc_now(),
        "url": bounded_url,
        "title": _redacted_title(raw.get("title")),
        "focus": _focus_snapshot(raw),
        "controls": [],
        "warnings": [],
        "lifecycle": lifecycle,
        "success": None
        if is_whole_site
        else {
            "condition": success_condition if goal == SUPPORTED_GOAL else None,
            "matched": bool(raw.get("successMatched"))
            if goal == SUPPORTED_GOAL and success_condition == "Message sent"
            else False,
        },
        "goalProgress": None if is_whole_site else _goal_progress(
            raw, goal, success_condition
        ),
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
                safe_control[key] = (
                    _optional_bool(control[key])
                    if key == "acceptedInput"
                    else bool(control[key])
                )
        if "characterCount" in control:
            safe_control["characterCount"] = _bounded_character_count(
                control["characterCount"]
            )
        safe_control.setdefault("focusable", True)
        observation["controls"].append(safe_control)
    if is_whole_site:
        observation["coverage"] = _coverage_progress(raw, covered_focus_ids)
    for warning in _lifecycle_warnings(raw_lifecycle):
        _append_warning(observation["warnings"], warning)
    if navigation_warning == "off-loopback-redirect":
        _append_warning(observation["warnings"], {"kind": "off-loopback-redirect"})
        observation["lifecycle"]["offLoopbackRedirect"] = True
    elif navigation_warning is not None:
        _append_warning(observation["warnings"], {"kind": navigation_warning})
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
    coordination = _TERMINAL_COORDINATION.get()
    lifecycle_lock, cancellation_requested = (
        coordination if coordination is not None else (None, None)
    )
    lock_context = lifecycle_lock if lifecycle_lock is not None else nullcontext()
    with lock_context:
        # The server's cancel endpoint uses this same lock to order requests
        # against terminalization.
        if cancellation_requested is not None and cancellation_requested():
            status = "INCONCLUSIVE"
            _append_warning(
                run.setdefault("warnings", []), {"kind": "run-cancelled"}
            )
        now = utc_now()
        run["status"] = status
        run["updatedAt"] = now
        run["completedAt"] = now
        run["durationMs"] = max(1, int((time.monotonic() - started) * 1000))
        run["interactionCount"] = len(run["actions"])
        success = observation.get("success")
        run["stoppingPoint"] = {
            "focus": observation["focus"],
            "successCondition": success.get("condition") if isinstance(success, dict) else None,
            "successMatched": success.get("matched") if isinstance(success, dict) else None,
            "goalProgress": observation["goalProgress"],
            "coverage": observation["coverage"],
            "observedAt": observation["observedAt"],
        }
        attach_evidence_handoff(run)


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


def _observation_progress_signature(
    observation: Dict[str, Any]
) -> Tuple[Any, Any, Any, Any]:
    return (
        observation.get("focus"),
        observation.get("success"),
        observation.get("goalProgress"),
        observation.get("coverage"),
    )


def _tab_scan_signature(observation: Dict[str, Any]) -> Tuple[Any, Any, Any]:
    focus = observation.get("focus")
    if not isinstance(focus, dict):
        focus = {}
    coverage = observation.get("coverage")
    if not isinstance(coverage, dict):
        coverage = {}
    return (
        focus.get("stableId") or focus.get("role") or focus.get("tag"),
        coverage.get("controlsObserved"),
        coverage.get("controlsExpected"),
    )


def _lifecycle_failure(observation: Dict[str, Any]) -> Optional[str]:
    lifecycle = observation.get("lifecycle", {})
    if not isinstance(lifecycle, dict):
        return "browser lifecycle evidence was invalid"
    if lifecycle.get("evidence") != "observed":
        return "browser lifecycle evidence is " + str(
            lifecycle.get("evidence", "missing")
        )
    if lifecycle.get("crashed"):
        return "browser page crashed"
    if lifecycle.get("browserLoadError"):
        return "the browser displayed a network error page instead of loading the selected website"
    if lifecycle.get("pageContentVisible") is False:
        return (
            "both isolated headless and headed Chrome sessions exposed an empty page"
            if lifecycle.get("headfulFallback")
            else "the page loaded without exposing visible content to the isolated browser"
        )
    if {"kind": "page-closed"} in observation.get("warnings", []):
        return "browser page closed"
    if lifecycle.get("offLoopbackRedirect"):
        return "browser navigated off the selected page origin"
    if lifecycle.get("navigationRedirect"):
        return "browser navigated to a different page on the target origin"
    return None


def _planner_action(planner: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    """Make at most two decisions for one unchanged observation."""
    errors = []
    for _ in range(2):
        try:
            # Give each attempt an isolated copy so a planner cannot mutate the
            # retry context and turn it into a different observation.
            decision = planner.next_action(copy.deepcopy(context))
            return validate_action(decision, context)
        except (PlannerError, TimeoutError) as error:
            errors.append(error)
    last_error = errors[-1] if errors else PlannerError("planner did not return an action")
    message = str(last_error).strip()[:160] or "planner did not return an action"
    failure = PlannerError(message)
    failure.attempts = 2
    raise failure from last_error


def _planner_failure_evidence(error: PlannerError) -> Dict[str, Any]:
    evidence = {
        "kind": "planner-failure",
        "attempts": int(getattr(error, "attempts", 1)),
    }
    message = str(error).strip()
    if message:
        evidence["message"] = message[:160]
    return evidence


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
    covered_focus_ids: Optional[set] = None,
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
                browser.observe(),
                run["targetUrl"],
                typed_values.values(),
                run.get("assessmentScope", "goal-focused"),
                run.get("goal"),
                covered_focus_ids,
                run.get("successCondition"),
            )
            run["observations"].append(current)
            _record_observation_warnings(run, current)
            failure = {
                "kind": "action-delivery-failure",
                "sequence": len(run["actions"]),
                "action": action["kind"],
            }
            if action["kind"] == "key":
                failure["key"] = action["key"]
            else:
                failure["field"] = action["field"]
                failure["characterCount"] = len(action["text"])
            _append_warning(current["warnings"], failure)
            _append_warning(run["warnings"], failure)
        except BrowserError as error:
            raise BrowserError(
                "browser action failed and could not be re-observed"
            ) from error
        raise ActionDeliveryFailure(
            "permitted keyboard action could not be delivered", current
        )
    _append_action(run, action, before, "delivered")
    observe_after_action = getattr(browser, "observe_focus", None)
    if not (
        run.get("assessmentScope") == "whole-site"
        and action.get("kind") == "key"
        and action.get("key") == "Tab"
        and callable(observe_after_action)
    ):
        observe_after_action = browser.observe
    current = _redacted_observation(
        observe_after_action(),
        run["targetUrl"],
        typed_values.values(),
        run.get("assessmentScope", "goal-focused"),
        run.get("goal"),
        covered_focus_ids,
        run.get("successCondition"),
    )
    run["observations"].append(current)
    _record_observation_warnings(run, current)
    if _observation_progress_signature(before) == _observation_progress_signature(current):
        failure = {
            "kind": "website-action-failure",
            "sequence": len(run["actions"]),
            "action": action["kind"],
        }
        if action["kind"] == "key":
            failure["key"] = action["key"]
        else:
            failure["field"] = action["field"]
            failure["characterCount"] = len(action["text"])
        if failure not in current["warnings"]:
            current["warnings"].append(failure)
        if failure not in run["warnings"]:
            run["warnings"].append(failure)
    lifecycle_failure = _lifecycle_failure(current)
    if lifecycle_failure is not None:
        raise BrowserError(lifecycle_failure)
    return current


def _settle_barrier_action(
    run: Dict[str, Any],
    browser: IsolatedKeyboardBrowser,
    action: Dict[str, Any],
    before: Dict[str, Any],
    typed_values: Dict[str, str],
    covered_focus_ids: Optional[set] = None,
) -> Dict[str, Any]:
    """Retry one barrier-probe delivery once after its fresh observation."""
    try:
        return _settle_action(
            run,
            browser,
            action,
            before,
            typed_values,
            covered_focus_ids,
        )
    except ActionDeliveryFailure as first_failure:
        current = first_failure.observation or before
        if _lifecycle_failure(current) is not None:
            raise
        try:
            return _settle_action(
                run,
                browser,
                action,
                current,
                typed_values,
                covered_focus_ids,
            )
        except ActionDeliveryFailure as second_failure:
            raise ActionDeliveryFailure(
                "permitted keyboard action failed twice during barrier probing",
                second_failure.observation or current,
                attempts=2,
            ) from second_failure


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
    covered_focus_ids: Optional[set] = None,
) -> Tuple[Dict[str, Any], bool]:
    if not _has_relevant_overlay(current):
        return current, False
    after = _settle_barrier_action(
        run,
        browser,
        {"kind": "key", "key": "Escape"},
        current,
        typed_values,
        covered_focus_ids,
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
    covered_focus_ids: Optional[set] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Probe a semantic Submit stopping point before calling it a barrier."""
    activation_actions = []
    activation_focus_consistent = True
    recovery_actions = []
    overlay_seen = False
    current = initial_submit

    current, dismissed_overlay = _dismiss_relevant_overlay(
        run, browser, current, typed_values, recovery_actions, covered_focus_ids
    )
    overlay_seen = dismissed_overlay

    for key in ("Enter", "Space"):
        before = current
        action_start = len(run["actions"])
        current = _settle_barrier_action(
            run,
            browser,
            {"kind": "key", "key": key},
            before,
            typed_values,
            covered_focus_ids,
        )
        activation_attempts = run["actions"][action_start:]
        activation_focus_consistent = activation_focus_consistent and bool(
            activation_attempts
        ) and all(
            action.get("kind") == "key"
            and action.get("key") == key
            and _same_submit_focus(
                initial_submit, {"focus": action.get("focusBefore", {})}
            )
            for action in activation_attempts
        )
        activation_actions.append(key)
        if current["success"]["matched"]:
            if not activation_focus_consistent:
                run.setdefault("recoveryEvidence", []).append(
                    {
                        "kind": "submit-barrier-recovery",
                        "attemptedActivations": activation_actions,
                        "activationFocusConsistent": False,
                        "actions": recovery_actions,
                        "initialFocus": _focus_snapshot(initial_submit),
                        "finalFocus": current["focus"],
                        "unchangedProgress": _unchanged_goal_progress(
                            initial_submit, current
                        ),
                        "sameSubmitFocus": _same_submit_focus(
                            initial_submit, current
                        ),
                        "successMatched": True,
                    }
                )
                _append_warning(
                    run["warnings"], {"kind": "barrier-evidence-inconclusive"}
                )
                _set_terminal_state(run, "INCONCLUSIVE", current, started)
                return "inconclusive", current
            if _complete_if_verified(
                run, current, started, browser, evidence_directory
            ):
                return "completed", current
            return "inconclusive", current
        current, dismissed_overlay = _dismiss_relevant_overlay(
            run, browser, current, typed_values, recovery_actions, covered_focus_ids
        )
        overlay_seen = overlay_seen or dismissed_overlay
        if not _same_submit_focus(initial_submit, current) or not _unchanged_goal_progress(
            initial_submit, current
        ):
            break

    for key in ("Shift+Tab", "Tab"):
        after = _settle_barrier_action(
            run,
            browser,
            {"kind": "key", "key": key},
            current,
            typed_values,
            covered_focus_ids,
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
        "activationFocusConsistent": activation_focus_consistent,
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
        and activation_focus_consistent
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


def _complete_with_screenshot(
    run: Dict[str, Any],
    observation: Dict[str, Any],
    started: float,
    browser: IsolatedKeyboardBrowser,
    evidence_directory: Optional[Path],
) -> bool:
    try:
        _persist_stopping_screenshot(run, browser, evidence_directory)
    except BrowserCleanupError:
        raise
    except BrowserError:
        _append_warning(
            run["warnings"],
            {
                "kind": "stopping-screenshot-unavailable",
                "message": "The run completed, but a redacted stopping screenshot could not be captured safely.",
            },
        )
    _set_terminal_state(run, "COMPLETED", observation, started)
    return True


def _complete_if_verified(
    run: Dict[str, Any],
    observation: Dict[str, Any],
    started: float,
    browser: IsolatedKeyboardBrowser,
    evidence_directory: Optional[Path],
) -> bool:
    if not observation["success"]["matched"] or not _submit_activation_observed(run):
        return False
    return _complete_with_screenshot(
        run, observation, started, browser, evidence_directory
    )


def _complete_whole_site_if_verified(
    run: Dict[str, Any],
    observation: Dict[str, Any],
    started: float,
    browser: IsolatedKeyboardBrowser,
    evidence_directory: Optional[Path],
) -> bool:
    coverage = observation.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("completed") is not True:
        return False
    return _complete_with_screenshot(
        run, observation, started, browser, evidence_directory
    )


def execute_assessment(
    run: Dict[str, Any],
    evidence_directory: Optional[Path] = None,
    planner: Optional[Any] = None,
    lifecycle_lock: Optional[Any] = None,
    cancellation_requested: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Execute a bounded whole-site or goal-focused keyboard assessment."""
    with BROWSER_RUN_LOCK:
        token = _TERMINAL_COORDINATION.set(
            (lifecycle_lock, cancellation_requested)
        )
        try:
            return _execute_assessment(run, evidence_directory, planner)
        finally:
            _TERMINAL_COORDINATION.reset(token)


def execute_contact_goal(
    run: Dict[str, Any],
    evidence_directory: Optional[Path] = None,
    planner: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute the supported fixed or broken contact-form goal."""
    if run.get("goal") != SUPPORTED_GOAL:
        raise ValueError("this lifecycle only supports the fixed contact-form goal")
    return execute_assessment(run, evidence_directory, planner)


def execute_fixed_goal(
    run: Dict[str, Any],
    evidence_directory: Optional[Path] = None,
    planner: Optional[Any] = None,
) -> Dict[str, Any]:
    """Backward-compatible public entry point for the fixed contact form."""
    if run.get("targetVersion") != "fixed":
        raise ValueError("this lifecycle only supports the fixed contact-form goal")
    return execute_contact_goal(run, evidence_directory, planner)


def _execute_assessment(
    run: Dict[str, Any], evidence_directory: Optional[Path], planner: Optional[Any]
) -> Dict[str, Any]:
    if run.get("targetVersion") not in {"fixed", "broken", "local", "web"}:
        raise ValueError("run has an unsupported target")
    if run.get("assessmentScope") not in {"whole-site", "goal-focused"}:
        raise ValueError("run has an unsupported assessment scope")
    if run.get("assessmentScope") == "whole-site" and run.get("goal") is not None:
        raise ValueError("whole-site runs cannot carry a goal")
    if run.get("assessmentScope") == "goal-focused" and run.get("goal") is None:
        raise ValueError("goal-focused runs require a goal")
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
    covered_focus_ids = set()
    try:
        if run.get("targetVersion") == "local":
            browser = IsolatedKeyboardBrowser(
                run["targetUrl"], restrict_network=True
            )
        else:
            browser = IsolatedKeyboardBrowser(run["targetUrl"])
        current_raw = browser.observe()
        if (
            run.get("targetVersion") == "web"
            and current_raw.get("lifecycle", {}).get("browserLoadError") is not True
            and browser.needs_headful_retry()
        ):
            headless_observation = _redacted_observation(
                current_raw,
                run["targetUrl"],
                typed_values.values(),
                run["assessmentScope"],
                run.get("goal"),
                covered_focus_ids,
                run.get("successCondition"),
            )
            run["observations"] = [headless_observation]
            headless_browser = browser
            browser = None
            headless_browser.close()
            try:
                browser = IsolatedKeyboardBrowser(
                    run["targetUrl"], headless=False
                )
                current_raw = browser.observe()
            except BrowserError as error:
                reason = (
                    "Headless Chrome exposed an empty page, and the isolated headed Chrome retry "
                    "could not finish navigation and page readiness within its bounded wait."
                )
                failure = {"kind": "headful-retry-failed", "message": reason[:160]}
                _append_warning(run["warnings"], failure)
                run["browserFailure"] = failure
                if run.get("goal") and run.get("goal") != SUPPORTED_GOAL:
                    headless_observation["goalProgress"] = _agent_goal_progress(
                        run["goal"], "not-possible", reason
                    )
                _set_terminal_state(
                    run, "INCONCLUSIVE", headless_observation, started
                )
                return run
        current = _redacted_observation(
            current_raw,
            run["targetUrl"],
            typed_values.values(),
            run["assessmentScope"],
            run.get("goal"),
            covered_focus_ids,
            run.get("successCondition"),
        )
        run["observations"] = [current]
        _record_observation_warnings(run, current)
        lifecycle_failure = _lifecycle_failure(current)
        if lifecycle_failure is not None:
            raise BrowserError(lifecycle_failure)

        consecutive_action_failures = 0
        tab_scan_states = set()
        while True:
            if run.get("assessmentScope") == "whole-site":
                coverage = current.get("coverage")
                if isinstance(coverage, dict) and coverage.get("completed") is True:
                    _complete_with_screenshot(
                        run, current, started, browser, evidence_directory
                    )
                    return run
                scan_state = _tab_scan_signature(current)
                if scan_state in tab_scan_states:
                    coverage = current.get("coverage")
                    if isinstance(coverage, dict):
                        coverage["status"] = "partial"
                    _append_warning(
                        run["warnings"],
                        {
                            "kind": "incomplete-coverage",
                            "message": (
                                "Keyboard focus traversal repeated before every detected control "
                                "was observed. The coverage score reflects the controls reached."
                            ),
                        },
                    )
                    _complete_with_screenshot(
                        run, current, started, browser, evidence_directory
                    )
                    return run
                tab_scan_states.add(scan_state)
                try:
                    current = _settle_action(
                        run,
                        browser,
                        {"kind": "key", "key": "Tab"},
                        current,
                        typed_values,
                        covered_focus_ids,
                    )
                    consecutive_action_failures = 0
                except ActionDeliveryFailure as error:
                    tab_scan_states.discard(scan_state)
                    consecutive_action_failures += 1
                    current = error.observation or current
                    lifecycle_failure = _lifecycle_failure(current)
                    if lifecycle_failure is not None or consecutive_action_failures >= 2:
                        reason = lifecycle_failure or "The browser could not deliver consecutive Tab actions."
                        failure = {
                            "kind": "action-delivery-failure",
                            "message": reason[:240],
                            "attempts": consecutive_action_failures,
                        }
                        _append_warning(run["warnings"], failure)
                        run["browserFailure"] = failure
                        _set_terminal_state(run, "INCONCLUSIVE", current, started)
                        return run
                continue

            if (
                run.get("assessmentScope") == "goal-focused"
                and run.get("goal") == SUPPORTED_GOAL
                and run.get("targetVersion") == "broken"
                and _is_submit_focus(current)
            ):
                barrier_status, current = _classify_broken_barrier(
                    run,
                    browser,
                    current,
                    started,
                    evidence_directory,
                    typed_values,
                    covered_focus_ids,
                )
                if barrier_status in {"blocked", "completed", "inconclusive"}:
                    return run

            screenshot_data_url = None
            capture_planner_screenshot = getattr(
                browser, "capture_planner_screenshot", None
            )
            if (
                callable(capture_planner_screenshot)
                and run.get("targetVersion") != "local"
            ):
                try:
                    screenshot_data_url = capture_planner_screenshot()
                except BrowserError:
                    # Screenshots are optional planner context. If capture or
                    # redaction fails, omit the image rather than use raw pixels.
                    screenshot_data_url = None
            if (
                not isinstance(screenshot_data_url, str)
                or not screenshot_data_url.startswith("data:image/png;base64,")
                or len(screenshot_data_url)
                > (MAX_PLANNER_SCREENSHOT_BYTES * 4 // 3) + 64
            ):
                screenshot_data_url = None

            bounded_for_planner = {
                "assessmentScope": run["assessmentScope"],
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
                    "successMatched": (
                        current["success"].get("matched")
                        if isinstance(current.get("success"), dict)
                        else None
                    ),
                    "screenshotAvailable": screenshot_data_url is not None,
                },
                "goalProgress": current["goalProgress"],
                "coverage": current["coverage"],
                "warnings": run["warnings"][-8:] + current["warnings"],
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
            if screenshot_data_url is not None:
                bounded_for_planner["pageEvidence"][
                    "screenshotDataUrl"
                ] = screenshot_data_url
            try:
                action = _planner_action(planner, bounded_for_planner)
            except PlannerError:
                current = _redacted_observation(
                    browser.observe(),
                    run["targetUrl"],
                    typed_values.values(),
                    run.get("assessmentScope", "goal-focused"),
                    run.get("goal"),
                    covered_focus_ids,
                    run.get("successCondition"),
                )
                run["observations"].append(current)
                _record_observation_warnings(run, current)
                lifecycle_failure = _lifecycle_failure(current)
                if lifecycle_failure is not None:
                    raise BrowserError(lifecycle_failure)
                raise
            if action["kind"] == "complete":
                current = _redacted_observation(
                    browser.observe(),
                    run["targetUrl"],
                    typed_values.values(),
                    run.get("assessmentScope", "goal-focused"),
                    run.get("goal"),
                    covered_focus_ids,
                    run.get("successCondition"),
                )
                run["observations"].append(current)
                _record_observation_warnings(run, current)
                lifecycle_failure = _lifecycle_failure(current)
                if lifecycle_failure is not None:
                    raise BrowserError(lifecycle_failure)
                if run.get("assessmentScope") == "whole-site":
                    coverage = current.get("coverage")
                    if isinstance(coverage, dict):
                        coverage["status"] = "partial"
                        _append_warning(
                            run["warnings"],
                            {
                                "kind": "incomplete-coverage",
                                "message": "The keyboard run completed with partial coverage; the score reports detected controls reached.",
                            },
                        )
                        _complete_with_screenshot(
                            run, current, started, browser, evidence_directory
                        )
                        return run
                    _append_warning(run["warnings"], {"kind": "incomplete-coverage"})
                    _set_terminal_state(run, "INCONCLUSIVE", current, started)
                    return run
                goal = run.get("goal")
                goal_status = action.get("goalStatus")
                goal_reason = action.get("goalReason")
                if goal is not None and goal != SUPPORTED_GOAL:
                    if goal_status == "completed":
                        current["goalProgress"] = _agent_goal_progress(
                            goal, "completed"
                        )
                        _complete_with_screenshot(
                            run, current, started, browser, evidence_directory
                        )
                    elif goal_status == "not-accessibility-related":
                        reason = goal_reason or "This goal is unrelated to website accessibility."
                        current["goalProgress"] = _agent_goal_progress(
                            goal, "not-accessibility-related", reason
                        )
                        _append_warning(
                            run["warnings"],
                            {"kind": "unrelated-goal", "message": reason[:240]},
                        )
                        _set_terminal_state(run, "INCONCLUSIVE", current, started)
                    else:
                        reason = goal_reason or (
                            "The agent could not complete this goal with the available browser actions."
                        )
                        current["goalProgress"] = _agent_goal_progress(
                            goal, "not-possible", reason
                        )
                        _append_warning(
                            run["warnings"],
                            {"kind": "goal-not-possible", "message": reason[:240]},
                        )
                        _set_terminal_state(run, "INCONCLUSIVE", current, started)
                    return run
                if _complete_if_verified(
                    run, current, started, browser, evidence_directory
                ):
                    return run
                if goal_status == "not-possible":
                    reason = goal_reason or "The agent could not complete the requested goal."
                    current["goalProgress"] = _agent_goal_progress(
                        goal or SUPPORTED_GOAL, "not-possible", reason
                    )
                    _append_warning(
                        run["warnings"],
                        {"kind": "goal-not-possible", "message": reason[:240]},
                    )
                    _set_terminal_state(run, "INCONCLUSIVE", current, started)
                    return run
                if goal_status == "completed":
                    current["goalProgress"] = _agent_goal_progress(
                        goal or SUPPORTED_GOAL,
                        "not-possible",
                        "The page did not show the expected success condition.",
                    )
                    _set_terminal_state(run, "INCONCLUSIVE", current, started)
                    return run
                raise PlannerError("planner stopped without locally verified success")
            try:
                current = _settle_action(
                    run,
                    browser,
                    action,
                    current,
                    typed_values,
                    covered_focus_ids,
                )
                if (
                    run.get("goal") is not None
                    and run.get("goal") != SUPPORTED_GOAL
                ):
                    current["goalProgress"] = _agent_goal_progress(
                        run["goal"],
                        action.get("goalStatus") or "in-progress",
                        action.get("goalReason"),
                    )
            except ActionDeliveryFailure as error:
                consecutive_action_failures += 1
                current = error.observation or current
                lifecycle_failure = _lifecycle_failure(current)
                if lifecycle_failure is not None:
                    failure = {
                        "kind": "page-content-unavailable"
                        if current.get("lifecycle", {}).get("pageContentVisible") is False
                        else "browser-failure",
                        "message": lifecycle_failure[:240],
                    }
                    _append_warning(run["warnings"], failure)
                    run["browserFailure"] = failure
                    if run.get("goal") and run.get("goal") != SUPPORTED_GOAL:
                        current["goalProgress"] = _agent_goal_progress(
                            run["goal"], "not-possible", lifecycle_failure
                        )
                        _append_warning(
                            run["warnings"],
                            {"kind": "goal-not-possible", "message": lifecycle_failure},
                        )
                    _set_terminal_state(run, "INCONCLUSIVE", current, started)
                    return run
                if consecutive_action_failures >= 2:
                    failure = {
                        "kind": "action-delivery-failure",
                        "attempts": consecutive_action_failures,
                    }
                    _append_warning(run["warnings"], failure)
                    run["browserFailure"] = failure
                    if run.get("goal") and run.get("goal") != SUPPORTED_GOAL:
                        reason = "The browser could not complete the requested goal action after two delivery attempts."
                        current["goalProgress"] = _agent_goal_progress(
                            run["goal"], "not-possible", reason
                        )
                        _append_warning(
                            run["warnings"],
                            {"kind": "goal-not-possible", "message": reason},
                        )
                    _set_terminal_state(run, "INCONCLUSIVE", current, started)
                    return run
                continue
            consecutive_action_failures = 0
            if run.get("assessmentScope") == "whole-site":
                if _complete_whole_site_if_verified(
                    run, current, started, browser, evidence_directory
                ):
                    return run
                continue
            if _complete_if_verified(
                run, current, started, browser, evidence_directory
            ):
                return run

    except PlannerError as error:
        planner_failure = _planner_failure_evidence(error)
        _append_warning(run["warnings"], planner_failure)
        run["agentFailure"] = planner_failure
        fallback = run["observations"][-1]
        if run.get("goal") and run.get("goal") != SUPPORTED_GOAL:
            reason = "The agent could not evaluate this goal because it did not return a usable action."
            fallback["goalProgress"] = _agent_goal_progress(
                run["goal"], "not-possible", reason
            )
            _append_warning(
                run["warnings"],
                {"kind": "goal-not-possible", "message": reason},
            )
        _set_terminal_state(run, "INCONCLUSIVE", fallback, started)
        return run
    except ActionDeliveryFailure as error:
        failure = {
            "kind": "action-delivery-failure",
            "attempts": int(getattr(error, "attempts", 1)),
        }
        _append_warning(run["warnings"], failure)
        run["browserFailure"] = failure
        fallback = error.observation or run["observations"][-1]
        if run.get("goal") and run.get("goal") != SUPPORTED_GOAL:
            reason = "The browser could not complete the requested goal action."
            fallback["goalProgress"] = _agent_goal_progress(
                run["goal"], "not-possible", reason
            )
            _append_warning(
                run["warnings"],
                {"kind": "goal-not-possible", "message": reason},
            )
        _set_terminal_state(run, "INCONCLUSIVE", fallback, started)
        return run
    except (BrowserError, BrowserActionError) as error:
        message = str(error).strip()
        page_content_unavailable = (
            "empty page" in message
            or "without exposing visible content" in message
        )
        failure = {
            "kind": "page-content-unavailable"
            if page_content_unavailable
            else "browser-failure"
        }
        if message:
            failure["message"] = message[:240]
        _append_warning(run["warnings"], failure)
        run["browserFailure"] = dict(failure)
        if isinstance(error, BrowserCleanupError):
            run["browserFailure"] = {"kind": "cleanup-failure"}
            run["browserSession"]["cleanup"] = {
                "status": "failed",
                "profileRemoved": False,
            }
        fallback = run["observations"][-1] if run.get("observations") else {
            "focus": {},
            "success": (
                None
                if run.get("assessmentScope") == "whole-site"
                else {
                    "condition": "Message sent"
                    if run.get("goal") == SUPPORTED_GOAL
                    else None,
                    "matched": False,
                }
            ),
            "goalProgress": (
                None
                if run.get("assessmentScope") == "whole-site"
                else {
                    "goal": run.get("goal"),
                    "status": "not-started",
                    "completed": False,
                    "support": "agent-evaluates",
                }
                if run.get("goal") != SUPPORTED_GOAL
                else {}
            ),
            "coverage": None,
            "observedAt": utc_now(),
        }
        if run.get("goal") and run.get("goal") != SUPPORTED_GOAL:
            reason = (
                "The browser showed a network error page instead of the selected website."
                if fallback.get("lifecycle", {}).get("browserLoadError")
                else "The browser stopped before the agent could complete the goal."
            )
            fallback["goalProgress"] = _agent_goal_progress(
                run["goal"], "not-possible", reason
            )
        _set_terminal_state(run, "INCONCLUSIVE", fallback, started)
        return run
    finally:
        if browser is not None:
            try:
                browser.close()
            except BrowserError:
                _append_warning(run["warnings"], {"kind": "browser-cleanup-failure"})
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
        attach_evidence_handoff(run)
