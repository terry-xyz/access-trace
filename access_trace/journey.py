"""The fixed contact-form keyboard journey and redacted evidence lifecycle."""

import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .browser import BrowserActionError, BrowserError, IsolatedKeyboardBrowser
from .domain import SUPPORTED_GOAL, utc_now


MAX_INTERACTIONS = 16
BROWSER_RUN_LOCK = threading.Lock()
BOUNDED_TYPED_VALUES = {
    "name": "Avery Example",
    "email": "avery@example.test",
    "message": "A fictional message",
}


class FixedContactFormPlanner:
    """Choose one permitted action from bounded, untrusted observations."""

    def next_action(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        page_evidence = observation.get("pageEvidence", observation)
        focus = page_evidence.get("focus", {})
        if page_evidence.get("successMatched"):
            return {"kind": "complete"}
        if focus.get("role") == "document":
            return {"kind": "key", "key": "Tab"}
        if focus.get("stableId") in BOUNDED_TYPED_VALUES and not focus.get("acceptedInput"):
            return {
                "kind": "type",
                "field": focus.get("stableId"),
                "value": BOUNDED_TYPED_VALUES[focus["stableId"]],
            }
        if focus.get("role") == "button" and focus.get("accessibleName") == "Submit":
            return {"kind": "key", "key": "Enter"}
        return {"kind": "key", "key": "Tab"}


def _focus_snapshot(observation: Dict[str, Any]) -> Dict[str, Any]:
    focus = observation.get("focus", {})
    return {
        "role": focus.get("role"),
        "accessibleName": focus.get("accessibleName"),
        "tag": focus.get("tag"),
        "stableId": focus.get("stableId"),
        "isStable": bool(focus.get("isStable")),
        "characterCount": focus.get("characterCount", 0),
        "acceptedInput": bool(focus.get("acceptedInput")),
        "validationState": focus.get("validationState", "not-observed"),
    }


def _goal_progress(observation: Dict[str, Any]) -> Dict[str, Any]:
    controls = observation.get("controls", [])
    fields = {}
    for control in controls:
        stable_id = control.get("stableId")
        if stable_id not in {"name", "email", "message"}:
            continue
        fields[stable_id] = {
            "characterCount": int(control.get("characterCount", 0)),
            "acceptedInput": bool(control.get("acceptedInput")),
            "validationState": control.get("validationState", "not-observed"),
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
        "submitFocused": observation.get("focus", {}).get("stableId") == "submit",
    }


def _redacted_observation(raw: Dict[str, Any], target_url: str) -> Dict[str, Any]:
    url = raw.get("url")
    parsed_target = target_url.split("/demo/", 1)[0]
    safe_url = url if isinstance(url, str) and url.startswith(parsed_target + "/demo/") else url
    observation = {
        "kind": "settled-observation",
        "observedAt": utc_now(),
        "url": safe_url,
        "title": raw.get("title"),
        "focus": _focus_snapshot(raw),
        "controls": [],
        "warnings": [],
        "lifecycle": raw.get("lifecycle", {}),
        "success": {
            "condition": "Message sent",
            "matched": bool(raw.get("successMatched")),
        },
        "goalProgress": _goal_progress(raw),
        "coverage": None,
    }
    for control in raw.get("controls", []):
        safe_control = {
            key: control[key]
            for key in (
                "role",
                "accessibleName",
                "tag",
                "stableId",
                "focusable",
                "isStable",
                "characterCount",
                "acceptedInput",
                "validationState",
            )
            if key in control
        }
        safe_control.setdefault("focusable", True)
        observation["controls"].append(safe_control)
    if not isinstance(safe_url, str) or not safe_url.startswith(parsed_target + "/demo/"):
        observation["warnings"].append({"kind": "off-loopback-redirect"})
        observation["lifecycle"]["offLoopbackRedirect"] = True
    return observation


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
    _set_terminal_state(run, "COMPLETED", observation, started)
    if evidence_directory is not None:
        run["stoppingScreenshotRef"] = browser.capture_redacted_screenshot(
            evidence_directory / (run["id"] + "-stopping.png")
        )
    return True


def execute_fixed_goal(
    run: Dict[str, Any], evidence_directory: Optional[Path] = None
) -> Dict[str, Any]:
    """Execute one fixed-goal run and return the durable, redacted record."""
    with BROWSER_RUN_LOCK:
        return _execute_fixed_goal(run, evidence_directory)


def _execute_fixed_goal(
    run: Dict[str, Any], evidence_directory: Optional[Path]
) -> Dict[str, Any]:
    if run.get("goal") != SUPPORTED_GOAL or run.get("targetVersion") != "fixed":
        raise ValueError("this lifecycle only supports the fixed contact-form goal")
    started = time.monotonic()
    run["startedAt"] = utc_now()
    run["browserSession"]["isolation"] = "fresh"
    run["browserSession"]["startedAt"] = run["startedAt"]
    run["agentFailure"] = None
    planner = FixedContactFormPlanner()
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
            action = planner.next_action(bounded_for_planner)
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
    except (BrowserError, BrowserActionError) as error:
        run["warnings"].append({"kind": "browser-failure", "message": str(error)})
        run["agentFailure"] = {"kind": "browser-failure"}
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
            browser.close()
        run["browserSession"]["closedAt"] = utc_now()
        run["updatedAt"] = utc_now()
