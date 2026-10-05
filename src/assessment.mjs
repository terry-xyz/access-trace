const MAX_GOAL_LENGTH = 500;

/** validateTargetUrl accepts absolute web URLs and uploaded local site routes. */
export function validateTargetUrl(value) {
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
