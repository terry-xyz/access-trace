"""Stable, redacted evidence handoff for downstream report consumers."""

from typing import Any, Dict, List, Optional

from .source_references import SOURCE_REFERENCES, source_reference
from .wcag import WCAG22_CRITERIA


EVIDENCE_SCHEMA = "access-trace.evidence.v1"
MAX_TEXT_LENGTH = 256
MAX_MESSAGE_LENGTH = 160
MAX_CHARACTER_COUNT = 100_000
MAX_RECOVERY_EVIDENCE = 32
REVIEW_UNAVAILABLE_REASON = "Evidence review is unavailable."
REPORTING_LIMITATION = (
    "Evidence for the configured keyboard assessment on the selected site; "
    "not a general accessibility or WCAG conformance assessment."
)
MAX_REPORT_CONDITIONS = 8
MAX_CONDITION_LENGTH = 240


def _text(value: Any, limit: int = MAX_TEXT_LENGTH) -> Optional[str]:
    if not isinstance(value, str):
        return None
    return value[:limit]


def _character_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(count, MAX_CHARACTER_COUNT))


def _optional_count(value: Any) -> Optional[int]:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if value >= 0 else None


def _optional_bool(value: Any) -> Optional[bool]:
    return None if value is None else bool(value)


def _input_state(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "characterCount": _character_count(source.get("characterCount", 0)),
        "acceptedInput": _optional_bool(source.get("acceptedInput")),
        "validationState": _text(source.get("validationState", "not-observed"), 80),
    }


def _focus(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "role": _text(source.get("role"), 80),
        "accessibleName": _text(source.get("accessibleName"), 80),
        "tag": _text(source.get("tag"), 80),
        "stableId": _text(source.get("stableId"), 80),
        "isStable": bool(source.get("isStable")),
        **_input_state(source),
    }


def _control(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    control: Dict[str, Any] = {}
    for key in ("role", "accessibleName", "tag", "stableId", "validationState"):
        if key in value:
            control[key] = _text(value[key], 80)
    for key in ("focusable", "isStable", "acceptedInput"):
        if key in value:
            control[key] = (
                _optional_bool(value[key])
                if key == "acceptedInput"
                else bool(value[key])
            )
    if "characterCount" in value:
        control["characterCount"] = _character_count(value["characterCount"])
    control.setdefault("focusable", True)
    return control


def _controls(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [control for item in value[:8] if (control := _control(item)) is not None]


def _success(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    return {
        "condition": _text(value.get("condition"), 80),
        "matched": bool(value.get("matched")),
    }


def _field_progress(value: Any) -> Dict[str, Any]:
    return _input_state(value)


def _goal_progress(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    progress: Dict[str, Any] = {
        "goal": _text(value.get("goal"), 500),
        "status": _text(value.get("status"), 40),
        "completed": _optional_bool(value.get("completed")),
        "support": _text(value.get("support"), 40),
    }
    if isinstance(value.get("reason"), str):
        progress["reason"] = _text(value["reason"], 240)
    for key in ("completedFields", "expectedFields"):
        progress[key] = _optional_count(value.get(key))
    if "submitFocused" in value:
        progress["submitFocused"] = _optional_bool(value["submitFocused"])
    fields = value.get("fields")
    if isinstance(fields, dict):
        progress["fields"] = {
            _text(field, 80): _field_progress(field_value)
            for field, field_value in fields.items()
            if isinstance(field, str) and _text(field, 80)
        }
    return progress


def _coverage(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    coverage: Dict[str, Any] = {
        "status": _text(value.get("status"), 40),
        "completed": _optional_bool(value.get("completed")),
        "areasObserved": _optional_count(value.get("areasObserved")),
        "areasExpected": _optional_count(value.get("areasExpected")),
        "controlsObserved": _optional_count(value.get("controlsObserved")),
        "controlsExpected": _optional_count(value.get("controlsExpected")),
        "scorePercentage": _optional_count(value.get("scorePercentage")),
        "controlsTruncated": _optional_bool(value.get("controlsTruncated")),
    }
    for key in ("visitedControls", "expectedControls"):
        raw_ids = value.get(key)
        coverage[key] = [
            _text(stable_id, 80)
            for stable_id in raw_ids[:8]
            if isinstance(stable_id, str)
        ] if isinstance(raw_ids, list) else None
    return coverage


def _lifecycle(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    result = {
        key: _optional_bool(source.get(key))
        for key in (
            "pageOpen",
            "dialogOpen",
            "dialogObserved",
            "popupObserved",
            "popupAttempted",
            "crashed",
            "offLoopbackRedirect",
            "navigationRedirect",
        )
    }
    result["evidence"] = _text(source.get("evidence"), 40)
    result["browserLoadError"] = _optional_bool(source.get("browserLoadError"))
    result["wwwHostFallback"] = _optional_bool(source.get("wwwHostFallback"))
    result["pageContentVisible"] = _optional_bool(source.get("pageContentVisible"))
    result["headfulFallback"] = _optional_bool(source.get("headfulFallback"))
    return result


def _warning(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    warning: Dict[str, Any] = {}
    if isinstance(value.get("kind"), str):
        warning["kind"] = _text(value["kind"], 80)
    for key in ("sequence", "attempts", "characterCount"):
        if key in value:
            warning[key] = _character_count(value[key])
    for key in ("action", "key", "field"):
        if isinstance(value.get(key), str):
            warning[key] = _text(value[key], 80)
    if isinstance(value.get("message"), str):
        warning["message"] = _text(value["message"], MAX_MESSAGE_LENGTH)
    return warning or None


def _warnings(values: Any) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    return [warning for item in values if (warning := _warning(item)) is not None]


def _observation(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "kind": _text(source.get("kind"), 40),
        "observedAt": _text(source.get("observedAt"), 80),
        "url": _text(source.get("url")),
        "title": _text(source.get("title"), 80),
        "focus": _focus(source.get("focus")),
        "controls": _controls(source.get("controls")),
        "success": _success(source.get("success")),
        "goalProgress": _goal_progress(source.get("goalProgress")),
        "coverage": _coverage(source.get("coverage")),
        "warnings": _warnings(source.get("warnings")),
        "lifecycle": _lifecycle(source.get("lifecycle")),
    }


def _action(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    action: Dict[str, Any] = {
        "sequence": _character_count(value.get("sequence", 0)),
        "kind": _text(value.get("kind"), 40),
        "allowed": bool(value.get("allowed")),
        "status": _text(value.get("status"), 40),
        "focusBefore": _focus(value.get("focusBefore")),
        "actedAt": _text(value.get("actedAt"), 80),
    }
    for key in ("key", "field"):
        if isinstance(value.get(key), str):
            action[key] = _text(value[key], 80)
    if "characterCount" in value:
        action["characterCount"] = _character_count(value["characterCount"])
    if "retained" in value:
        action["retained"] = bool(value["retained"])
    return action


def _actions(
    values: Any, observations: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    actions = [action for item in values if (action := _action(item)) is not None]
    for action in actions:
        sequence = action["sequence"]
        if (
            observations is not None
            and isinstance(sequence, int)
            and 0 <= sequence < len(observations)
        ):
            action["focusAfter"] = observations[sequence]["focus"]
    return actions


def _recovery_step(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    step: Dict[str, Any] = {}
    for key in ("key", "status"):
        if isinstance(value.get(key), str):
            step[key] = _text(value[key], 80)
    for key in ("focusBefore", "focusAfter"):
        if key in value:
            step[key] = _focus(value[key])
    return step or None


def _recovery(value: Any, sequence: int) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    attempted_activations = value.get("attemptedActivations")
    attempted_activations = (
        attempted_activations[:8]
        if isinstance(attempted_activations, list)
        else []
    )
    recovery: Dict[str, Any] = {
        "sequence": sequence,
        "kind": _text(value.get("kind"), 80),
        "attemptedActivations": [
            _text(key, 80)
            for key in attempted_activations
            if isinstance(key, str)
        ],
        "activationFocusConsistent": bool(value.get("activationFocusConsistent")),
        "actions": [
            step
            for item in value.get("actions", [])[:8]
            if (step := _recovery_step(item)) is not None
        ] if isinstance(value.get("actions"), list) else [],
        "initialFocus": _focus(value.get("initialFocus")),
        "finalFocus": _focus(value.get("finalFocus")),
        "unchangedProgress": bool(value.get("unchangedProgress")),
        "sameSubmitFocus": bool(value.get("sameSubmitFocus")),
        "localFocusRecovery": bool(value.get("localFocusRecovery")),
        "wholePageWrapped": bool(value.get("wholePageWrapped")),
        "successMatched": bool(value.get("successMatched")),
    }
    return recovery


def _recoveries(values: Any) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    recoveries = []
    for item in values[:MAX_RECOVERY_EVIDENCE]:
        recovery = _recovery(item, len(recoveries) + 1)
        if recovery is not None:
            recoveries.append(recovery)
    return recoveries


def _stopping_point(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    return {
        "focus": _focus(value.get("focus")),
        "successCondition": _text(value.get("successCondition"), 80),
        "successMatched": (
            bool(value["successMatched"])
            if value.get("successMatched") is not None
            else None
        ),
        "goalProgress": _goal_progress(value.get("goalProgress")),
        "coverage": _coverage(value.get("coverage")),
        "observedAt": _text(value.get("observedAt"), 80),
    }


def _browser_session(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    cleanup = source.get("cleanup")
    safe_cleanup = None
    if isinstance(cleanup, dict):
        safe_cleanup = {
            "status": _text(cleanup.get("status"), 40),
            "profileRemoved": bool(cleanup.get("profileRemoved")),
        }
    return {
        "isolation": _text(source.get("isolation"), 40),
        "startedAt": _text(source.get("startedAt"), 80),
        "closedAt": _text(source.get("closedAt"), 80),
        "cleanup": safe_cleanup,
    }


def _screenshot_ref(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value or "/" in value or "\\" in value:
        return None
    return value[:128]


def _references(
    actions: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    recoveries: List[Dict[str, Any]],
    screenshot_ref: Optional[str],
) -> List[Dict[str, Any]]:
    references = [
        {"kind": "action", "sequence": action["sequence"]}
        for action in actions
    ]
    references.extend(
        {"kind": "observation", "sequence": index}
        for index, _ in enumerate(observations, start=1)
    )
    references.extend(
        {"kind": "recovery", "sequence": recovery["sequence"]}
        for recovery in recoveries
    )
    if screenshot_ref is not None:
        references.append(
            {
                "kind": "stopping-screenshot",
                "ref": screenshot_ref,
                "redacted": True,
            }
        )
    return references


def _evidence_reference_id(value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if not isinstance(kind, str):
        return None
    if kind in {"action", "observation", "recovery"}:
        sequence = _optional_count(value.get("sequence"))
        if sequence is not None and 0 < sequence <= MAX_CHARACTER_COUNT:
            return "{}:{}".format(kind, sequence)
        return None
    if kind == "stopping-screenshot" and value.get("redacted") is True:
        screenshot_ref = _screenshot_ref(value.get("ref"))
        return "stopping-screenshot" if screenshot_ref is not None else None
    return None


def _reporting_reference(
    value: Any, allowed_references: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    reference_id = value.get("id")
    if not isinstance(kind, str) or not isinstance(reference_id, str):
        return None
    if kind in {"action", "observation", "recovery"}:
        sequence = _optional_count(value.get("sequence"))
        if sequence is None or sequence == 0 or sequence > MAX_CHARACTER_COUNT:
            return None
        if reference_id != "{}:{}".format(kind, sequence):
            return None
        locator = {"id": reference_id, "kind": kind, "sequence": sequence}
        return locator if allowed_references.get(reference_id) == locator else None
    if kind == "stopping-screenshot":
        screenshot_ref = _screenshot_ref(value.get("ref"))
        if (
            reference_id != "stopping-screenshot"
            or screenshot_ref is None
            or value.get("redacted") is not True
        ):
            return None
        locator = {
            "id": reference_id,
            "kind": kind,
            "ref": screenshot_ref,
            "redacted": True,
        }
        return locator if allowed_references.get(reference_id) == locator else None
    return None


def _reporting_condition(
    value: Any, allowed_references: Dict[str, Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Keep one condition only when its source mapping and citations are valid."""
    if not isinstance(value, dict):
        return None
    condition = value.get("condition")
    status = value.get("mappingStatus")
    criterion = value.get("wcagCriterion")
    cited_source = value.get("sourceReference")
    references = value.get("evidenceReferences")
    if (
        not isinstance(condition, str) or not condition.strip()
        or len(condition) > MAX_CONDITION_LENGTH
        or not isinstance(status, str) or status not in {"mapped", "source", "unmapped"}
        or not isinstance(references, list) or not references or len(references) > 16
    ):
        return None
    if status == "unmapped":
        if criterion is not None or cited_source is not None:
            return None
        safe_criterion = None
        safe_source = None
    elif status == "source":
        if criterion is not None or not isinstance(cited_source, dict):
            return None
        source_id = cited_source.get("id")
        if not isinstance(source_id, str) or source_id not in SOURCE_REFERENCES:
            return None
        safe_source = source_reference(source_id)
        if cited_source != safe_source:
            return None
        safe_criterion = None
    else:
        if not isinstance(criterion, dict) or cited_source is not None:
            return None
        criterion_id = criterion.get("id")
        if not isinstance(criterion_id, str) or criterion_id not in WCAG22_CRITERIA:
            return None
        name, slug = WCAG22_CRITERIA[criterion_id]
        safe_criterion = {
            "id": criterion_id,
            "name": name,
            "url": "https://www.w3.org/TR/WCAG22/#" + slug,
        }
        if criterion != safe_criterion:
            return None
        safe_source = None
    safe_references = [
        _reporting_reference(item, allowed_references) for item in references
    ]
    if (
        any(reference is None for reference in safe_references)
        or len({reference["id"] for reference in safe_references}) != len(safe_references)
    ):
        return None
    return {
        "condition": condition,
        "mappingStatus": status,
        "wcagCriterion": safe_criterion,
        "sourceReference": safe_source,
        "evidenceReferences": safe_references,
    }


def _reporting(
    value: Any, evidence_references: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Preserve only the bounded reporting state across handoff refreshes."""
    pending = {
        "status": "pending",
        "explanation": None,
        "evidenceReferences": [],
        "confidence": None,
        "proposedFix": None,
        "conditions": [],
        "reason": None,
        "limitation": REPORTING_LIMITATION,
    }
    if not isinstance(value, dict):
        return pending
    if value.get("status") == "unavailable":
        return {
            **pending,
            "status": "unavailable",
            "reason": REVIEW_UNAVAILABLE_REASON,
        }
    if value.get("status") != "available":
        return pending

    explanation = value.get("explanation")
    confidence = value.get("confidence")
    references = value.get("evidenceReferences")
    proposed_fix = value.get("proposedFix")
    raw_conditions = value.get("conditions", [])
    if (
        not isinstance(explanation, str)
        or not explanation.strip()
        or len(explanation) > 600
        or not isinstance(confidence, str)
        or confidence not in {"low", "medium", "high"}
        or not isinstance(references, list)
        or not references
        or len(references) > 16
        or not isinstance(raw_conditions, list)
        or len(raw_conditions) > MAX_REPORT_CONDITIONS
        or (
            proposed_fix is not None
            and (
                not isinstance(proposed_fix, str)
                or not proposed_fix.strip()
                or len(proposed_fix) > 500
            )
        )
    ):
        return pending
    allowed_references = {}
    for item in evidence_references:
        reference_id = _evidence_reference_id(item)
        if reference_id is not None:
            if reference_id in allowed_references:
                return pending
            allowed_references[reference_id] = {**item, "id": reference_id}
    safe_references = [
        _reporting_reference(item, allowed_references) for item in references
    ]
    if (
        any(reference is None for reference in safe_references)
        or len({reference["id"] for reference in safe_references})
        != len(safe_references)
    ):
        return pending
    safe_conditions = [
        _reporting_condition(item, allowed_references) for item in raw_conditions
    ]
    if any(condition is None for condition in safe_conditions):
        return pending
    return {
        **pending,
        "status": "available",
        "explanation": explanation,
        "evidenceReferences": safe_references,
        "confidence": confidence,
        "proposedFix": proposed_fix,
        "conditions": safe_conditions,
    }


def build_evidence_handoff(run: Dict[str, Any]) -> Dict[str, Any]:
    """Project a run into the stable contract consumed by report work."""
    assessment = {
        "targetUrl": _text(run.get("targetUrl")),
        "targetVersion": _text(run.get("targetVersion"), 40),
        "assessmentScope": _text(run.get("assessmentScope"), 40),
        "goal": _text(run.get("goal"), 500),
        "pageOnly": bool(run.get("pageOnly")),
        "sitePageLimit": run.get("sitePageLimit"),
        "successCondition": _text(run.get("successCondition"), 80),
        "simulationMode": bool(run.get("simulationMode")),
        "interactionProfile": _text(run.get("interactionProfile"), 40),
    }
    observations = [
        _observation(item)
        for item in run.get("observations", [])
    ] if isinstance(run.get("observations"), list) else []
    actions = _actions(run.get("actions"), observations)
    screenshot_ref = _screenshot_ref(run.get("stoppingScreenshotRef"))
    final_observation = observations[-1] if observations else {}
    stopping_point = run.get("stoppingPoint")
    progress_source = (
        stopping_point if isinstance(stopping_point, dict) else final_observation
    )
    raw_actions = run.get("actions")
    raw_observations = run.get("observations")
    raw_recoveries = run.get("recoveryEvidence")
    recoveries = _recoveries(raw_recoveries)
    evidence_references = _references(actions, observations, recoveries, screenshot_ref)
    run_status = _text(run.get("status"), 40)
    statistics = {
        "terminalStatus": (
            run_status
            if run_status in {"COMPLETED", "BLOCKED", "INCONCLUSIVE"}
            else None
        ),
        "durationMs": _optional_count(run.get("durationMs")),
        "interactionCount": _optional_count(run.get("interactionCount")),
        "goalProgress": _goal_progress(progress_source.get("goalProgress")),
        "coverage": _coverage(progress_source.get("coverage")),
        "actionCount": (
            len(raw_actions) if isinstance(raw_actions, list) else None
        ),
        "observationCount": (
            len(raw_observations) if isinstance(raw_observations, list) else None
        ),
        "recoveryCount": (
            len(raw_recoveries) if isinstance(raw_recoveries, list) else None
        ),
    }
    comparison_settings = {
        key: assessment[key]
        for key in (
            "assessmentScope",
            "goal",
            "pageOnly",
            "sitePageLimit",
            "successCondition",
            "simulationMode",
            "interactionProfile",
        )
    }

    return {
        "schema": EVIDENCE_SCHEMA,
        "runId": _text(run.get("id"), 80),
        "assessment": assessment,
        "timing": {
            "createdAt": _text(run.get("createdAt"), 80),
            "startedAt": _text(run.get("startedAt"), 80),
            "completedAt": _text(run.get("completedAt"), 80),
            "updatedAt": _text(run.get("updatedAt"), 80),
            "durationMs": (
                _character_count(run["durationMs"])
                if run.get("durationMs") is not None
                else None
            ),
        },
        "interactionCount": _character_count(run.get("interactionCount", len(actions))),
        "actions": actions,
        "observations": observations,
        "focusObservations": [
            {
                "sequence": index,
                "observedAt": observation["observedAt"],
                "url": observation["url"],
                "title": observation["title"],
                "focus": observation["focus"],
            }
            for index, observation in enumerate(observations, start=1)
        ],
        "progress": {
            "goal": _goal_progress(final_observation.get("goalProgress")),
            "coverage": _coverage(final_observation.get("coverage")),
        },
        "stopping": {
            "point": _stopping_point(run.get("stoppingPoint")),
            "screenshotRef": screenshot_ref,
        },
        "terminal": {
            "status": _text(run.get("status"), 40),
            "warnings": _warnings(run.get("warnings")),
            "recoveryEvidence": recoveries,
            "agentFailure": _warning(run.get("agentFailure")),
            "browserFailure": _warning(run.get("browserFailure")),
            "browserSession": _browser_session(run.get("browserSession")),
        },
        "stats": statistics,
        "evidenceReferences": evidence_references,
        "comparison": {
            "settings": comparison_settings,
            "target": {
                "targetUrl": assessment["targetUrl"],
                "targetVersion": assessment["targetVersion"],
            },
            "runCount": 1,
        },
        "reporting": _reporting(
            run.get("evidenceHandoff", {}).get("reporting")
            if isinstance(run.get("evidenceHandoff"), dict)
            else None,
            evidence_references,
        ),
        "privacy": {
            "rawValuesRetained": False,
            "pasteDataRetained": False,
            "pageSourceRetained": False,
            "stoppingScreenshotRedacted": True if screenshot_ref else None,
        },
    }


def attach_evidence_handoff(run: Dict[str, Any]) -> Dict[str, Any]:
    """Refresh the report-facing projection on the durable run object."""
    run["evidenceHandoff"] = build_evidence_handoff(run)
    return run
