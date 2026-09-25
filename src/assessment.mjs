export const CONTROLLED_TARGET_URL = "http://127.0.0.1:4173/";

const TARGET_ERROR = `Use the controlled local demo at ${CONTROLLED_TARGET_URL}`;
const UNSAFE_GOAL_PATTERNS = [
  /\b(?:ignore|override|disregard)\b.*\b(?:instructions|rules|safeguards|guardrails)\b/i,
  /\b(?:run|execute)\b.*\b(?:javascript|shell commands?|arbitrary code)\b/i,
];
const REMOTE_TARGET_PATTERN = /\b(?:remote|external|off[- ]site|off[- ]target|third[- ]party)\b|\b(?:another|other)\s+(?:site|website)\b|(?:https?:\/\/|www\.)\S+/i;
const OTHER_INPUT_MODE_PATTERN = /\b(?:mouse|touchscreen|touch screen|voice commands?|screen reader)\b/i;
const SECURITY_RESULT_PATTERN = /\b(?:securely|safely|privately|confidentially|encrypt\w*|vulnerab\w*|insecure\w*)\b|\b(?:is|are|be|remains?|becomes?|seems?|stays?)\s+(?:not\s+)?(?:secure|safe|private|confidential|encrypted|vulnerable)\b/i;
const SECURITY_TOPIC_PATTERN = /\b(?:security|privacy)\b/i;
const SECURITY_LABEL_MODIFIERS = "policy|settings?";
const SECURITY_LABEL_CONTROL_WORDS = `page|menu|link|button|field|control|element|dialog|tab|${SECURITY_LABEL_MODIFIERS}`;
const SITE_CONTROL_WORDS = `site|website|form|navigation|${SECURITY_LABEL_CONTROL_WORDS}`;
const SITE_CONTROL_PATTERN = new RegExp(`\\b(?:${SITE_CONTROL_WORDS})\\b`, "i");
const SECURITY_CONTROL_LABEL_PATTERN = new RegExp(
  `\\b(?:security|privacy)(?:\\s+(?:${SECURITY_LABEL_MODIFIERS}))?\\s+(?:${SECURITY_LABEL_CONTROL_WORDS})\\b`,
  "i",
);
const SECURITY_EVALUATION_PATTERN = /\b(?:assess|audit|evaluate|review|analyze|measure|score|rate|inspect|determine|ensure)\b/i;
const SECURITY_CHECK_PATTERN = /\b(?:check|test|verify|confirm)\b/i;
const SECURITY_CRITERION_PATTERN = /\b(?:adequat\w*|compliance|conformance|risk|posture)\b/i;
const SENSITIVE_DATA_PATTERN = /\b(?:passwords?|credentials?|authentication|authorization)\b/i;
const SENSITIVE_DATA_HANDLING_PATTERN = /\b(?:strength|policy|stor\w*|transmit\w*|protect\w*|hash\w*|expos\w*|leak\w*|share\w*)\b/i;
const NON_KEYBOARD_CRITERIA_PATTERN = /\b(?:color|colour)\s+contrast\b|\b(?:alt(?:ernative)?\s+text|image descriptions?)\b|\bwcag\s+(?:conformance|compliance)\b/i;
const KEYBOARD_GOAL_CUE_PATTERN = /\b(?:keyboard|keys?|tab(?:bing| order)?|enter|space|arrow keys?|shift[-+ ]?tab|focus|navigate|navigation)\b/i;
const IMPLICIT_KEYBOARD_ACTION_PATTERN = /\b(?:focus|navigate|move|reach|activate|open|close|select|expand|collapse|submit|send|fill|operate)\b/i;

const UNSAFE_GOAL_ERROR = "This goal asks to override assessment safeguards or execute code, so it cannot be assessed and will not be reinterpreted.";
const UNSUPPORTED_GOAL_ERROR = "Unsupported goal: this preview accepts free-text goals describing concrete keyboard interactions with named controls on the controlled local site. It cannot assess remote or off-site targets, other input modes, security or privacy evaluations, visual criteria, or other non-keyboard criteria. This goal will not be reinterpreted.";
const SECURITY_GOAL_ERROR = "Unsupported security/privacy goal: this preview cannot assess whether a site or form is secure, private, or handles sensitive data safely. It accepts keyboard interactions and outcomes only; this goal will not be reinterpreted.";

/** describesKeyboardGoal requires a concrete action on a named control; keyboard input is the assessment profile. */
function describesKeyboardGoal(candidate) {
  return hasActionOnSiteControl(candidate);
}

/** hasActionOnSiteControl shares the action-and-control boundary used by both keyboard classifiers. */
function hasActionOnSiteControl(candidate) {
  return IMPLICIT_KEYBOARD_ACTION_PATTERN.test(candidate) && SITE_CONTROL_PATTERN.test(candidate);
}

/** targetsSecurityControlLabel allows sensitive words only when they name the control being operated. */
function targetsSecurityControlLabel(candidate) {
  return hasActionOnSiteControl(candidate) && SECURITY_CONTROL_LABEL_PATTERN.test(candidate);
}

/** describesSecurityAssessment looks for security assertions, not security-related control names. */
function describesSecurityAssessment(candidate) {
  // Explicit security outcomes are out of scope, while words used only as control labels are not.
  if (SECURITY_RESULT_PATTERN.test(candidate)) return true;

  // Explicit evaluation or criterion language stays out of scope even when the goal also mentions keyboard use.
  const evaluatesSecurityTopic = SECURITY_TOPIC_PATTERN.test(candidate)
    && (SECURITY_EVALUATION_PATTERN.test(candidate)
      || SECURITY_CRITERION_PATTERN.test(candidate)
      || (SECURITY_CHECK_PATTERN.test(candidate) && !targetsSecurityControlLabel(candidate)));

  // Sensitive fields are not themselves security requests; their handling must be the assessment subject.
  const evaluatesSensitiveDataHandling = SENSITIVE_DATA_PATTERN.test(candidate)
    && SENSITIVE_DATA_HANDLING_PATTERN.test(candidate);

  return evaluatesSecurityTopic || evaluatesSensitiveDataHandling;
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

  if (describesSecurityAssessment(candidate)) {
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
