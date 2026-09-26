/** isSafeSourcePath accepts only normalized relative paths inside the selected folder. */
export function isSafeSourcePath(path) {
  if (typeof path !== "string" || !path || path.startsWith("/") || path.includes("\\") || path.includes("\0")) {
    return false;
  }
  return !path.split("/").some((part) => !part || part === "." || part === "..");
}

/** validateApplicableFiles limits a server proposal to reviewed files with unique paths. */
export function validateApplicableFiles(reviewedFiles, applicableFiles) {
  if (!Array.isArray(reviewedFiles) || !Array.isArray(applicableFiles) || applicableFiles.length === 0) {
    throw new Error("The approval response did not contain changed files.");
  }
  const reviewedPaths = new Set(reviewedFiles.map(({ path }) => path));
  const seen = new Set();
  for (const file of applicableFiles) {
    if (!file || !isSafeSourcePath(file.path) || typeof file.content !== "string") {
      throw new Error("The approval response contained an invalid file.");
    }
    if (!reviewedPaths.has(file.path)) {
      throw new Error(`The patch refers to an unreviewed file: ${file.path}.`);
    }
    if (seen.has(file.path)) throw new Error(`The patch contains duplicate file paths: ${file.path}.`);
    seen.add(file.path);
  }
  return applicableFiles;
}

/** hasPersistedSourceBaseline checks whether a saved proposal can be matched to local files. */
export function hasPersistedSourceBaseline(review) {
  if (!review || typeof review !== "object" || !Array.isArray(review.relevantPaths) || !review.relevantPaths.length) {
    return false;
  }
  const digests = review.sourceDigests;
  return Boolean(digests && typeof digests === "object")
    && review.relevantPaths.every((path) => typeof path === "string" && typeof digests[path] === "string");
}

/** canApproveSourceReview allows current-session files or a verifiable saved proposal. */
export function canApproveSourceReview(reviewedFileCount, review) {
  return reviewedFileCount > 0
    || (review?.status === "PATCH_READY" && hasPersistedSourceBaseline(review));
}

/** getSourceReviewActions keeps persisted proposals visible without stale local write handles. */
export function getSourceReviewActions(status, hasCurrentRunFiles, hasApprovalBaseline) {
  const normalizedStatus = typeof status === "string" ? status.toUpperCase() : "";
  const hasSavedReview = ["IN_PROGRESS", "PATCH_READY", "NO_PATCH", "FAILED", "CANCELLED"].includes(normalizedStatus);
  return {
    showFix: hasCurrentRunFiles && ["NOT_REQUESTED", "FAILED", "CANCELLED"].includes(normalizedStatus),
    showApprove: normalizedStatus === "PATCH_READY" && hasApprovalBaseline,
    showSavedReview: Boolean(hasCurrentRunFiles || hasSavedReview),
  };
}
