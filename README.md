# AccessTrace

AccessTrace runs the app, demo pages, and assessment API from one local server.
A live run starts a fresh keyboard-only browser session and presents its recorded
evidence. Demo comparisons execute real runs against the built-in fixed and
broken pages.

## Run AccessTrace

Requirements: Python 3.9 or later, the Codex CLI signed in to the developer's
Codex account, and Google Chrome or Chromium for live browser runs. If needed,
sign in once with `codex login`. No OpenAI API key or planner endpoint/model
configuration is required.

From the repository root, start the single server:

```sh
python3 -m access_trace --port 8080
```

Use this AccessTrace command rather than Python's `http.server`: the app's
server provides the UI, demo documents, uploaded local pages, and assessment API.

Open <http://127.0.0.1:8080/>. The demos are ordinary HTML, CSS, and JavaScript
files under `docs/demos/`, served as documents:

- <http://127.0.0.1:8080/docs/demos/fixed/index.html>
- <http://127.0.0.1:8080/docs/demos/broken/index.html>

Enter any absolute HTTP or HTTPS page URL, or choose an HTML file with its
supporting files or a site folder. AccessTrace uploads selected site files to an
opaque local path and puts that page URL in the target field. Folder paths are
preserved so relative CSS, JavaScript, image, and font references work. The
uploaded page runs in a sandbox with network requests disabled; only assets from
the uploaded local folder can load.

After a `BLOCKED`, `COMPLETED`, or `INCONCLUSIVE` result, if you selected code
context files or uploaded a local page folder, the report offers **Fix**. Fix starts a separate source review only when
pressed; selected file contents are not read or sent to the server or signed-in
Codex CLI before then. The reviewer explains the root cause and suggests a fix
when the evidence supports one. It may return no patch when the source and run
evidence do not support a specific change. Review the explanation and patch, then
choose **Approve and apply** to write the proposed changes to your source files.
AI-generated suggestions can be incorrect or introduce security issues. Review
the full patch and have a developer check it before applying it to a client site.
Saved proposals remain visible after a page reload; Approve asks for the source
folder again and checks its files against the saved digests before writing.

Applying a fix requires a browser with the File System Access API, currently
available in Chromium-based desktop browsers, and a local project folder selected
through the browser's folder picker. The File System Access API requires a secure
context and a user action; AccessTrace's loopback address provides the secure
context, and the folder picker is shown after you press Approve. It requests
read/write access. Choose the project folder containing the reviewed files at
the same relative paths shown in the report. Before writing, AccessTrace checks
that each target still matches the contents used for the review. If a file has
changed, the apply step stops and asks you to run Fix again. If your browser does
not support folder access, you can download the patch and apply it with your usual
tools. If a write fails after earlier files were written, the report identifies
the files already changed; apply or revert those changes before retrying.

Supported UTF-8 text files are filtered for common generated/dependency folders
and size limits. Folder selections also use best-effort `.gitignore` rules;
individually selected files bypass those rules. The matcher supports common glob
syntax with fixed limits; if it cannot safely filter a folder, including when its
`.gitignore` is oversized or unreadable as UTF-8 text, folder-selected files are
skipped and reported. Binary, unsupported, ignored, oversized, and prompt-budget-
excluded files are also skipped and reported with their reasons. Source text is
held only for the active review or approval request and discarded afterward,
including on error. The report stores the review explanation, relevant paths,
skipped path/reason metadata, generated patch, and source-content digests used to
detect changes. It does not store the original source contents. Source files are
never executed. The server prepares replacement text from the patch; the browser
writes it only after you approve and grant folder access.

Web URLs are opened in a fresh isolated browser. The browser follows the target
site while blocking popups and reporting off-site navigation. Uploaded local
pages have a stricter network policy and cannot submit forms or make connections.

Enter a web URL or choose local page files, then select **Start assessment**.
The app shows run progress and the live report when the assessment finishes.
AccessTrace invokes the installed Codex CLI with the saved login and validates
each returned keyboard action locally. Planner actions remain limited to
keyboard input and bounded fictional text. The fixed and broken demos support
the goal `Submit the contact form`; leave the goal empty for a whole-page
keyboard assessment. **Report** opens the latest completed run in this page;
**Compare demos** runs fresh checks against the built-in demos.

Redacted run records are written under `.access-trace/runs/`. The live result
can also be viewed or downloaded from the page. To use a different port, change
`8080` in the command and open that port in the browser.
