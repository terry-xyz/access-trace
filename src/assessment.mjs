export const CONTROLLED_TARGET_URL = "http://127.0.0.1:4173/";

const TARGET_ERROR = `Use the controlled local demo at ${CONTROLLED_TARGET_URL}`;

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
