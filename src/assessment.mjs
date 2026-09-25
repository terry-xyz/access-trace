export const CONTROLLED_TARGET_URL = "http://127.0.0.1:4173/";

const TARGET_ERROR = `Use the controlled local demo at ${CONTROLLED_TARGET_URL}`;
const UNSAFE_GOAL_PATTERNS = [
  /\b(?:ignore|override|disregard)\b.*\b(?:instructions|rules|safeguards|guardrails)\b/i,
  /\b(?:run|execute)\b.*\b(?:javascript|shell commands?|arbitrary code)\b/i,
];
const REMOTE_TARGET_PATTERN = /\b(?:remote|external|off[- ]site|off[- ]target|third[- ]party)\b|\b(?:another|other)\s+(?:site|website)\b|(?:https?:\/\/|www\.)\S+/i;
const OTHER_INPUT_MODE_PATTERN = /\b(?:mouse|touchscreen|touch screen|voice commands?|screen reader)\b/i;
const SECURITY_GOAL_PATTERN = /\b(?:secure\w*|security|privacy|encrypt\w*|credentials?|passwords?|authentication|authorization)\b/i;
const NON_KEYBOARD_CRITERIA_PATTERN = /\b(?:color|colour)\s+contrast\b|\b(?:alt(?:ernative)?\s+text|image descriptions?)\b|\bwcag\s+(?:conformance|compliance)\b/i;
const KEYBOARD_GOAL_CUE_PATTERN = /\b(?:keyboard|keys?|tab(?:bing| order)?|enter|space|arrow keys?|shift[-+ ]?tab|focus|navigate|navigation)\b/i;
const SITE_CONTROL_PATTERN = /\b(?:site|website|page|form|menu|link|button|field|control|dialog|navigation|element)\b/i;
const IMPLICIT_KEYBOARD_ACTION_PATTERN = /\b(?:reach|activate|open|close|select|expand|collapse|submit|send|fill|operate)\b/i;

const UNSAFE_GOAL_ERROR = "This goal asks to override assessment safeguards or execute code, so it cannot be assessed and will not be reinterpreted.";
const UNSUPPORTED_GOAL_ERROR = "Unsupported goal: this preview accepts free-text goals about keyboard interactions and outcomes on the controlled local site. It cannot assess remote or off-site targets, other input modes, security or visual criteria, or other non-keyboard criteria. This goal will not be reinterpreted.";
const SECURITY_GOAL_ERROR = "Unsupported security goal: this preview cannot assess whether a site or form is secure. It accepts keyboard interactions and outcomes only; this goal will not be reinterpreted.";

/** describesKeyboardGoal recognizes explicit keyboard evidence or a keyboard action tied to a site control. */
function describesKeyboardGoal(candidate) {
  // The keyboard profile is fixed, so an explicit keyboard/focus cue is sufficient to establish this goal's mode.
  if (KEYBOARD_GOAL_CUE_PATTERN.test(candidate)) return true;

  // Without that cue, require both a concrete interaction and a named control so a vague outcome is not inferred.
  return IMPLICIT_KEYBOARD_ACTION_PATTERN.test(candidate) && SITE_CONTROL_PATTERN.test(candidate);
}

/** validateTargetUrl accepts only the normalized controlled endpoint so other loopback services remain out of scope. */
export function validateTargetUrl(value) {
  const candidate = typeof value === "string" ? value.trim() : "";

  if (candidate === "") {
    return {
      valid: false,
      normalizedUrl: "",
      message: "Enter the controlled local demo address.",
    };
  }

  try {
    const normalizedUrl = new URL(candidate).href;
    if (normalizedUrl === CONTROLLED_TARGET_URL) {
      return { valid: true, normalizedUrl, message: "" };
    }
  } catch {
    return {
      valid: false,
      normalizedUrl: "",
      message: "Enter a valid URL for the controlled local demo.",
    };
  }

  return { valid: false, normalizedUrl: "", message: TARGET_ERROR };
}

/** getAssessmentScope treats an empty goal as a whole-site assessment and any supplied text as goal-focused. */
export function getAssessmentScope(goal) {
  return typeof goal === "string" && goal.trim() !== ""
    ? "goal-focused"
    : "whole-site";
}

/** validateAssessmentGoal preserves valid free text when it describes a keyboard task within the local-site boundary. */
export function validateAssessmentGoal(value) {
  const rawGoal = typeof value === "string" ? value : "";
  const candidate = rawGoal.trim();
  const scope = getAssessmentScope(rawGoal);

  if (scope === "whole-site") {
    return { valid: true, scope, goal: "", reason: "", message: "" };
  }

  if (UNSAFE_GOAL_PATTERNS.some((pattern) => pattern.test(candidate))) {
    return {
      valid: false,
      scope,
      goal: rawGoal,
      reason: "unsafe",
      message: UNSAFE_GOAL_ERROR,
    };
  }

  if (SECURITY_GOAL_PATTERN.test(candidate)) {
    return {
      valid: false,
      scope,
      goal: rawGoal,
      reason: "unsupported",
      message: SECURITY_GOAL_ERROR,
    };
  }

  const describesOutOfScopeGoal = REMOTE_TARGET_PATTERN.test(candidate)
    || OTHER_INPUT_MODE_PATTERN.test(candidate)
    || NON_KEYBOARD_CRITERIA_PATTERN.test(candidate);

  if (describesOutOfScopeGoal || !describesKeyboardGoal(candidate)) {
    return {
      valid: false,
      scope,
      goal: rawGoal,
      reason: "unsupported",
      message: UNSUPPORTED_GOAL_ERROR,
    };
  }

  return { valid: true, scope, goal: rawGoal, reason: "", message: "" };
}

/** calculateWebsiteScore reports the passed-to-attempted website-check ratio without grading agent failures. */
export function calculateWebsiteScore(passed, attempted) {
  if (
    !Number.isSafeInteger(passed) ||
    !Number.isSafeInteger(attempted) ||
    passed < 0 ||
    attempted < 0 ||
    passed > attempted
  ) {
    throw new RangeError("Website check counts must be non-negative whole numbers, with passed no greater than attempted.");
  }

  if (attempted === 0) {
    return {
      passed: 0,
      attempted: 0,
      percentage: null,
      label: "No website checks attempted",
    };
  }

  return {
    passed,
    attempted,
    percentage: Math.round((passed / attempted) * 100),
    label: `${passed} of ${attempted} website checks passed`,
  };
}
