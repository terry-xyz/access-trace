export const CONTROLLED_TARGET_URL = "http://127.0.0.1:4173/";
const MAX_GOAL_LENGTH = 500;

/** validateTargetUrl accepts absolute web URLs and uploaded local site routes. */
export function validateTargetUrl(value, baseOrigin = CONTROLLED_TARGET_URL) {
  const candidate = typeof value === "string" ? value.trim() : "";

  if (candidate === "") {
    return {
      valid: false,
      normalizedUrl: "",
      message: "Enter a URL or choose local page files.",
    };
  }

  try {
    const target = new URL(candidate);
    const normalizedUrl = target.href;
    if (
      ["http:", "https:"].includes(target.protocol)
      && target.hostname
      && !target.username
      && !target.password
    ) {
      return { valid: true, normalizedUrl, message: "" };
    }
  } catch {
    return {
      valid: false,
      normalizedUrl: "",
      message: "Enter a valid HTTP or HTTPS URL, or choose local page files.",
    };
  }

  return {
    valid: false,
    normalizedUrl: "",
    message: "Enter an absolute HTTP or HTTPS URL, or choose local page files.",
  };
}

/** getAssessmentScope treats an empty goal as a whole-site assessment and any supplied text as goal-focused. */
export function getAssessmentScope(goal) {
  return typeof goal === "string" && goal.trim() !== ""
    ? "goal-focused"
    : "whole-site";
}

/** validateAssessmentGoal accepts freeform objectives for the planner to assess within its bounded browser capabilities. */
export function validateAssessmentGoal(value) {
  const rawGoal = typeof value === "string" ? value : "";
  const candidate = rawGoal.trim();
  const scope = getAssessmentScope(rawGoal);

  if (scope === "whole-site") {
    return { valid: true, scope, goal: "", reason: "", message: "" };
  }
  if (candidate.length > MAX_GOAL_LENGTH) {
    return {
      valid: false,
      scope,
      goal: candidate,
      reason: "too-long",
      message: `Keep the goal to ${MAX_GOAL_LENGTH} characters or fewer.`,
    };
  }

  return { valid: true, scope, goal: candidate, reason: "", message: "" };
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
