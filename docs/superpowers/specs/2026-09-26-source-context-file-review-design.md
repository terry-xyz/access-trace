# Source Context File Review Design

## Goal

Let a user attach one or more files or a folder as read-only source context for an HTTP target assessment. The browser assessment remains the primary check; source review runs afterward only when the browser records a repeatable keyboard barrier that needs a fix.

## Decisions

- The selected URL remains the assessment target. Supporting files do not replace it or get served to the browser.
- Users can select multiple files or a folder. Folder-relative paths are retained.
- The source review uses relevant text-based source, configuration, and documentation files. Common generated/dependency folders are skipped for both folder and individual-file selections. `.gitignore` rules apply to folder selections; individually selected files remain eligible when their names match those rules. A best-effort matcher supports nested ignore files, comments, negation, escaped comment/negation prefixes, leading-slash anchoring, trailing-slash directory rules, `*`, `?`, character classes, and `**` with bounded NFA matching. It caps paths at 4 KiB, patterns at 1 KiB, total rules at 10,000, and matching work at 20 million state transitions per manifest. It does not implement all Git escaping and ignored-parent re-inclusion behavior. If a matcher limit is exceeded or a directory-selected `.gitignore` is oversized, binary, or invalid UTF-8, directory-origin files are skipped and reported rather than reviewed with incomplete ignore filtering.
- The existing browser journey and its planner contract remain separate and unchanged. A distinct read-only Codex review receives the terminal browser evidence and selected source context only after a `BLOCKED` result.
- The reviewer may return a reviewable unified patch. It must not modify uploaded files or execute uploaded code.
- Original source content is held only for the active source-review request and is discarded on success, timeout, cancellation, or error. Cleanup clears source text while retaining skipped path/reason metadata for the run report. The durable run record may retain the review status, concise explanation, relevant paths, and generated patch.
- If there is no supported issue, no source context, or no evidence-backed code change, the run reports that no patch was produced.
- Existing target URL validation and network boundaries remain unchanged.

## Flow

1. The setup form keeps its target URL and presents separate multiple-file and folder selectors for optional source context. The browser retains selected `File` objects locally while the assessment runs.
2. The server runs and persists the existing browser assessment first. No source-file content is sent to the server or Codex during this stage.
3. If the terminal result is `BLOCKED` and source files are selected, the browser sends their text and relative paths to a separate post-assessment source-review endpoint. If no issue is found, the files are never read or uploaded.
4. The endpoint validates and filters the files in memory. A separate Codex call receives bounded run evidence and filtered source text. The call has no write or network capability and must return a structured result containing either no supported fix or a unified patch.
5. The server validates that patch paths refer only to supplied files, records the result on the run, and discards source contents on success, timeout, cancellation, or error.
6. The report shows source-review status and any patch in a safely rendered code block, with a patch download. It also states that files are sent to the signed-in Codex only when a blocked run triggers source review.

## Failure handling

- Invalid paths (including paths over 4 KiB, absolute paths, and Windows drive-prefixed paths), malformed payloads, more than 200 files, NUL text, and a serialized request larger than 5 MiB fail with a clear request error.
- An individual file larger than 512 KiB, invalid UTF-8 text, unsupported binary text, `.gitignore` matches, generated/dependency-directory matches, or files beyond the 32 KiB per-file and 64 KiB aggregate reviewer budgets are skipped with their paths and reasons. Whole files omitted to keep the Codex process argument within the platform-safe prompt limit are also skipped and reported. If any ignore matcher limit is exceeded, directory-origin files are skipped with a matching-limit reason. These per-file skips do not reject an otherwise valid request; the 5 MiB request limit remains a hard rejection.
- Individually selected files bypass `.gitignore` filtering, but still skip common generated/dependency directories and obey file and reviewer size limits.
- Review timeout, cancellation, authentication failure, malformed output, or a patch that refers to unprovided files produces no patch and does not change the browser assessment result.
- The source review is a second stage; its failure is recorded separately from browser and planner failures.

## Boundaries

This feature does not change which HTTP targets AccessTrace accepts, does not serve source files, does not run uploaded code, does not change source files, and does not claim a fix is correct merely because a patch was generated.
