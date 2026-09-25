"""Public data contract for the first Journey & Evidence run boundary."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit


SUPPORTED_GOAL = "Submit the contact form"
INTERACTION_PROFILE = "keyboard-only"
DEFAULT_SIMULATION_MODE = True
CONTROLLED_SCHEME = "http"
DEMO_TITLE = "AccessTrace Contact form"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
SUPPORTED_TARGET_PATHS = {
    "/demo/fixed": "fixed",
    "/demo/broken": "broken",
}


class ValidationError(ValueError):
    """Raised when a run request is outside the controlled local boundary."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_target_url(
    target_url: Any, controlled_port: int, controlled_scheme: str = CONTROLLED_SCHEME
) -> Tuple[str, str]:
    if not isinstance(target_url, str) or not target_url.strip():
        raise ValidationError("targetUrl must be a non-empty absolute URL")

    parsed = urlsplit(target_url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/") or "/"

    try:
        port = parsed.port
    except ValueError:
        raise ValidationError("targetUrl must use a valid local port")

    if parsed.scheme != controlled_scheme:
        raise ValidationError("targetUrl must use the controlled server scheme")
    if host not in LOOPBACK_HOSTS:
        raise ValidationError("targetUrl must point to the controlled local site")
    effective_port = port if port is not None else 80
    if effective_port != controlled_port:
        raise ValidationError("targetUrl must use the controlled server port")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValidationError("targetUrl must not contain credentials, a query, or a fragment")
    if path not in SUPPORTED_TARGET_PATHS:
        raise ValidationError("targetUrl must select the fixed or broken controlled demo")

    normalized = parsed._replace(path=path).geturl()
    return normalized, SUPPORTED_TARGET_PATHS[path]


def normalize_goal(goal: Any) -> Optional[str]:
    if goal is None:
        return None
    if not isinstance(goal, str):
        raise ValidationError("goal must be text when supplied")
    normalized = goal.strip()
    if not normalized:
        return None
    if len(normalized) > 200:
        raise ValidationError("goal must be 200 characters or fewer")
    return normalized


def build_run_request(
    payload: Dict[str, Any], controlled_port: int, controlled_scheme: str = CONTROLLED_SCHEME
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")

    target_url, target_version = validate_target_url(
        payload.get("targetUrl"), controlled_port, controlled_scheme
    )
    goal = normalize_goal(payload.get("goal"))
    derived_scope = "goal-focused" if goal is not None else "whole-site"
    requested_scope = payload.get("assessmentScope")
    if requested_scope is not None and requested_scope != derived_scope:
        raise ValidationError(
            "assessmentScope must match whether a goal is supplied"
        )

    simulation_mode = payload.get("simulationMode", DEFAULT_SIMULATION_MODE)
    if not isinstance(simulation_mode, bool):
        raise ValidationError("simulationMode must be boolean")

    return {
        "targetUrl": target_url,
        "targetVersion": target_version,
        "assessmentScope": derived_scope,
        "goal": goal,
        "simulationMode": simulation_mode,
    }


def _controls() -> list:
    return [
        {
            "role": "textbox",
            "accessibleName": "Name",
            "tag": "input",
            "stableId": "name",
            "focusable": True,
            "characterCount": 0,
            "acceptedInput": None,
            "validationState": "not-observed",
        },
        {
            "role": "textbox",
            "accessibleName": "Email",
            "tag": "input",
            "stableId": "email",
            "focusable": True,
            "characterCount": 0,
            "acceptedInput": None,
            "validationState": "not-observed",
        },
        {
            "role": "textbox",
            "accessibleName": "Message",
            "tag": "textarea",
            "stableId": "message",
            "focusable": True,
            "characterCount": 0,
            "acceptedInput": None,
            "validationState": "not-observed",
        },
        {
            "role": "button",
            "accessibleName": "Submit",
            "tag": "button",
            "stableId": "submit",
            "focusable": True,
        },
    ]


def first_observation(run_request: Dict[str, Any]) -> Dict[str, Any]:
    goal = run_request["goal"]
    observation = {
        "kind": "settled-observation",
        "observedAt": utc_now(),
        "url": run_request["targetUrl"],
        "title": DEMO_TITLE,
        "focus": {
            "role": "document",
            "accessibleName": "Fictional contact form",
            "tag": "body",
            "stableId": "document",
            "isStable": True,
        },
        "controls": _controls(),
        "warnings": [],
        "lifecycle": {
            "pageOpen": True,
            "dialogOpen": False,
            "popupObserved": False,
            "crashed": False,
            "offLoopbackRedirect": False,
        },
    }

    if goal is None:
        observation["success"] = None
        observation["goalProgress"] = None
        observation["coverage"] = {
            "status": "not-started",
            "completed": False,
            "areasObserved": 0,
            "areasExpected": 1,
        }
    else:
        observation["success"] = {
            "condition": "Message sent" if goal == SUPPORTED_GOAL else None,
            "matched": False,
        }
        observation["goalProgress"] = {
            "goal": goal,
            "status": "not-started",
            "completed": False,
        }
        observation["coverage"] = None

    return observation


def create_run(
    payload: Dict[str, Any], controlled_port: int, controlled_scheme: str = CONTROLLED_SCHEME
) -> Dict[str, Any]:
    run_request = build_run_request(payload, controlled_port, controlled_scheme)
    now = utc_now()
    run_id = str(uuid.uuid4())
    observation = first_observation(run_request)
    return {
        "schemaVersion": 1,
        "id": run_id,
        "status": "IN_PROGRESS",
        "createdAt": now,
        "updatedAt": now,
        "targetUrl": run_request["targetUrl"],
        "targetVersion": run_request["targetVersion"],
        "assessmentScope": run_request["assessmentScope"],
        "goal": run_request["goal"],
        "successCondition": (
            "Message sent" if run_request["goal"] == SUPPORTED_GOAL else None
        ),
        "simulationMode": run_request["simulationMode"],
        "interactionProfile": INTERACTION_PROFILE,
        "browserSession": {
            "id": str(uuid.uuid4()),
            "isolation": "fresh",
        },
        "startedAt": None,
        "completedAt": None,
        "durationMs": None,
        "interactionCount": 0,
        "actions": [],
        "observations": [observation],
        "warnings": [],
        "recoveryEvidence": [],
        "stoppingPoint": None,
        "stoppingScreenshotRef": None,
        "agentFailure": None,
        "browserFailure": None,
    }
