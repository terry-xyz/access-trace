"""Public data contract for the first Journey & Evidence run boundary."""

import uuid
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

from .evidence import attach_evidence_handoff


SUPPORTED_GOAL = "Submit the contact form"
INTERACTION_PROFILE = "keyboard-only"
DEFAULT_SIMULATION_MODE = True
CONTROLLED_SCHEME = "http"
DEMO_TITLE = "AccessTrace Contact form"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
SUPPORTED_TARGET_PATHS = {
    "/docs/demos/fixed/index.html": "fixed",
    "/docs/demos/broken/index.html": "broken",
}
LOCAL_HTML_TARGET_PATTERN = re.compile(r"^/sites/([0-9a-f]{32})/(.+)$")


class ValidationError(ValueError):
    """Raised when a run request does not satisfy the public input contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_target_url(
    target_url: Any, controlled_port: int, controlled_scheme: str = CONTROLLED_SCHEME
) -> Tuple[str, str]:
    if not isinstance(target_url, str) or not target_url.strip():
        raise ValidationError("targetUrl must be a non-empty absolute URL")

    parsed = urlsplit(target_url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    if len(target_url) > 2048:
        raise ValidationError("targetUrl must be 2048 characters or fewer")

    try:
        port = parsed.port
    except ValueError:
        raise ValidationError("targetUrl must use a valid local port")

    if parsed.scheme not in {"http", "https"} or not host:
        raise ValidationError("targetUrl must be an absolute HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise ValidationError("targetUrl must not contain embedded credentials")

    effective_port = port if port is not None else (443 if parsed.scheme == "https" else 80)
    is_controlled_origin = (
        parsed.scheme == controlled_scheme
        and host in LOOPBACK_HOSTS
        and effective_port == controlled_port
    )
    uploaded_site = LOCAL_HTML_TARGET_PATTERN.fullmatch(path)
    if is_controlled_origin and path in SUPPORTED_TARGET_PATHS:
        target_version = SUPPORTED_TARGET_PATHS[path]
    elif is_controlled_origin and uploaded_site:
        target_version = "local"
    else:
        target_version = "web"

    normalized = parsed.geturl()
    return normalized, target_version


def normalize_goal(goal: Any) -> Optional[str]:
    if goal is None:
        return None
    if not isinstance(goal, str):
        raise ValidationError("goal must be text when supplied")
    normalized = goal.strip()
    if not normalized:
        return None
    if len(normalized) > 500:
        raise ValidationError("goal must be 500 characters or fewer")
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
    page_only = payload.get("pageOnly", False)
    if not isinstance(page_only, bool):
        raise ValidationError("pageOnly must be boolean")

    return {
        "targetUrl": target_url,
        "targetVersion": target_version,
        "assessmentScope": derived_scope,
        "goal": goal,
        "pageOnly": page_only,
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
    target_version = run_request["targetVersion"]
    is_controlled_demo = target_version in {"fixed", "broken"}
    supports_contact_goal = is_controlled_demo
    observation = {
        "kind": "settled-observation",
        "observedAt": utc_now(),
        "url": run_request["targetUrl"],
        "title": DEMO_TITLE if is_controlled_demo else None,
        "focus": {
            "role": "document",
            "accessibleName": "Fictional contact form" if is_controlled_demo else None,
            "tag": "body",
            "stableId": "document",
            "isStable": True,
        },
        "controls": _controls() if is_controlled_demo else [],
        "warnings": [],
        "lifecycle": {
            "pageOpen": None,
            "dialogOpen": None,
            "dialogObserved": None,
            "popupObserved": None,
            "popupAttempted": None,
            "crashed": None,
            "offLoopbackRedirect": None,
            "navigationRedirect": None,
            "evidence": "not-observed",
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
            "controlsObserved": 0,
            "controlsExpected": 0,
            "visitedControls": [],
            "expectedControls": [],
            "controlsTruncated": False,
        }
    else:
        observation["success"] = {
            "condition": "Message sent"
            if supports_contact_goal and goal == SUPPORTED_GOAL
            else None,
            "matched": False,
        }
        observation["goalProgress"] = {
            "goal": goal,
            "status": "not-started",
            "completed": False,
            "support": (
                "supported"
                if supports_contact_goal and goal == SUPPORTED_GOAL
                else "agent-evaluates"
            ),
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
    run = {
        "schemaVersion": 1,
        "id": run_id,
        "status": "IN_PROGRESS",
        "createdAt": now,
        "updatedAt": now,
        "targetUrl": run_request["targetUrl"],
        "targetVersion": run_request["targetVersion"],
        "assessmentScope": run_request["assessmentScope"],
        "goal": run_request["goal"],
        "pageOnly": run_request["pageOnly"],
        "successCondition": (
            "Message sent"
            if run_request["targetVersion"] in {"fixed", "broken"}
            and run_request["goal"] == SUPPORTED_GOAL
            else None
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
    return attach_evidence_handoff(run)
