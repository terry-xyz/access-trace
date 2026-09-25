export const CONTROLLED_TARGET_URL = "http://127.0.0.1:4173/";

const TARGET_ERROR = `Use the controlled local demo at ${CONTROLLED_TARGET_URL}`;
const UNSAFE_GOAL_PATTERNS = [
  /\b(?:ignore|override|disregard)\b.*\b(?:instructions|rules|safeguards|guardrails)\b/i,
  /\b(?:run|execute)\b.*\b(?:javascript|shell commands?|arbitrary code)\b/i,
];
const UNSUPPORTED_GOAL_PATTERNS = [
  /https?:\/\/\S+/i,
  /\b(?:mouse|touchscreen|touch screen|voice commands?|screen reader)\b/i,
  /\b(?:wcag (?:conformance|compliance)|full accessibility (?:audit|assessment|score))\b/i,
];

const UNSAFE_GOAL_ERROR = "This goal asks to override assessment safeguards or execute code, so it cannot be assessed.";
const UNSUPPORTED_GOAL_ERROR = "Unsupported goal: this preview accepts keyboard goals for the controlled local demo and cannot assess remote sites, other interaction modes, or full-conformance requests.";

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

/** validateAssessmentGoal keeps free text intact and rejects only clearly unsafe or out-of-bound requests. */
export function validateAssessmentGoal(value) {
  const goal = typeof value === "string" ? value.trim() : "";
  const scope = getAssessmentScope(goal);

  if (scope === "whole-site") {
    return { valid: true, scope, goal: "", reason: "", message: "" };
  }

  if (UNSAFE_GOAL_PATTERNS.some((pattern) => pattern.test(goal))) {
    return {
      valid: false,
      scope,
      goal,
      reason: "unsafe",
      message: UNSAFE_GOAL_ERROR,
    };
  }

  if (UNSUPPORTED_GOAL_PATTERNS.some((pattern) => pattern.test(goal))) {
    return {
      valid: false,
      scope,
      goal,
      reason: "unsupported",
      message: UNSUPPORTED_GOAL_ERROR,
    };
  }

  return { valid: true, scope, goal, reason: "", message: "" };
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
