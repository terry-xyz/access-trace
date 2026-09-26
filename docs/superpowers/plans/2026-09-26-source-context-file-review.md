# Source Context File Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the standalone HTML target upload with optional files/folder context that can produce a reviewable source patch after a blocked browser assessment.

**Architecture:** Keep the current target URL and browser journey unchanged. Retain selected browser `File` objects during the site check; only after a `BLOCKED` result send bounded text and relative paths to a separate read-only source-review request. Persist the returned patch on the run while uploaded source content is discarded.

**Tech Stack:** Python standard library HTTP server, browser ES modules, Codex CLI.

---

## File boundaries

- `access_trace/source_context.py` will validate the file manifest, enforce upload bounds, preserve relative paths, apply ignore rules, identify text files, and provide cleanup-safe context for a run.
- `access_trace/source_review.py` will build the bounded source-review prompt, invoke Codex in an isolated read-only turn, and validate structured review output and patch paths.
- `access_trace/server.py` will add a post-assessment source-review endpoint, preserve reviewer cancellation and error handling, and persist only review output.
- `index.html` will separate target URL selection from optional source-context file/folder selection and add patch presentation.
- `src/main.mjs` will retain selected files during the browser assessment, then send supported relative paths and text to the separate source-review endpoint only after `BLOCKED`; it will update stage/status copy and render/download a returned patch using text nodes.
- `src/styles.css` will style the patch review block using existing report styles.
- `README.md` will document file/folder context, post-assessment review, and source retention behavior.

## Task 1: Build the source-context and source-review boundary

**Files:**
- Create: `access_trace/source_context.py`
- Create: `access_trace/source_review.py`

- [x] Accept the `{"files":[{"path":"src/example.py","content":"..."}]}` manifest payload passed by the post-assessment endpoint. Enforce at most 200 files and a hard 5 MiB serialized request limit; reject paths over 4 KiB, absolute or Windows drive-prefixed paths, parent traversal, duplicate paths, NUL text, and non-string entries. Skip and report individual files over 512 KiB or with unsupported binary/invalid UTF-8 text.
- [x] Preserve nested relative paths and report skipped path/reason metadata. Skip common generated/dependency folders for all selections; apply best-effort bounded `.gitignore` matching only to directory selections. Cap patterns at 1 KiB, total rules at 10,000, and matcher work at 20 million state transitions; skip and report directory-origin files if an ignore matcher limit is exceeded or its `.gitignore` is oversized, binary, or invalid UTF-8. Individually selected files bypass `.gitignore` matches.
- [x] Limit reviewer source text to 64 KiB total and one file to 32 KiB. If the budget is exceeded, omit whole files in stable path order and list their names as skipped. Keep the serialized Codex prompt within platform-safe process-argument limits, omitting and reporting whole files when necessary. Mark run evidence and source contents as untrusted data in the prompt.
- [x] Implement a separate Codex CLI call with a 60-second timeout and a strict output schema for review status, a 2,000-character explanation, relevant paths, and a unified patch of at most 20,000 characters. Keep tool, write, and network capabilities disabled.
- [x] Reject invalid output and patches that mention paths outside the supplied source manifest. Return a no-patch state rather than a guessed fix when evidence is insufficient.
- [x] Keep source contents in memory only and provide explicit cleanup on every return and failure path.

## Task 2: Integrate the second stage into run execution

**Files:**
- Modify: `access_trace/server.py`

- [x] Keep the existing execute request and target validation unchanged. Add a separate `POST /api/runs/{id}/source-review` endpoint with a 5 MiB body cap that accepts the optional `sourceContext.files` manifest only for a completed `BLOCKED` run.
- [x] Invoke the source reviewer only from that endpoint, after the browser has completed; reject review requests for non-`BLOCKED` runs and prevent concurrent reviews of one run.
- [x] Track active source reviewers separately from keyboard planners. Allow cancellation to stop an active source review and do not attach a patch from a cancelled review.
- [x] Store only source-review status, summary, relevant paths, and patch text on the run record. Never persist original uploaded file contents.
- [x] Record review failures separately, preserve the browser terminal status, persist the review result on the already completed run, and release source context in `finally`. The existing `IN_PROGRESS` and terminal browser-run persistence remains in place.

## Task 3: Replace the HTML target upload with source context

**Files:**
- Modify: `index.html`
- Modify: `src/main.mjs`
- Modify: `src/styles.css`

- [x] Replace the one-file HTML loader with a multiple-file selector and a folder selector. Keep both separate from the target URL field and show selected/skipped file counts.
- [x] Read selected files as strict UTF-8 text, preserve `webkitRelativePath`, apply fast client-side exclusions for common generated folders, and show a clear message for binary, ignored, or oversized files.
- [x] Keep the execute request unchanged. Only after it returns `BLOCKED`, send selected context to the source-review endpoint and show a second review stage; for other results, do not read or send selected file contents.
- [x] Render the review summary and unified patch with `textContent`; provide a `.patch` download when a valid patch exists.
- [x] Update privacy help to say source files are sent to signed-in Codex only for post-assessment review and are not retained.

## Task 4: Update product documentation

**Files:**
- Modify: `README.md`

- [x] Replace standalone HTML upload instructions with the HTTP target plus optional source-context workflow and explain the blocked-only review trigger.
- [x] Document that source files are filtered, never served or executed, and deleted after review while the report and patch remain.

## Review constraints

- Do not change the HTTP target allowlist, browser isolation, keyboard planner prompt, or page-evidence boundary.
- Do not run uploaded code or apply generated changes to uploaded files.
- This implementation session must not add or run tests. Review the final diff and report that automated tests were not run.
