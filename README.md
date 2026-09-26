# AccessTrace

AccessTrace runs the app, the fixed and broken demo pages, and the assessment API
from one local server. The report and comparison previews are representative
sample data; a live run starts a fresh keyboard-only browser session and shows
the redacted run record.

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
server provides the demo pages and assessment API as well as the UI.

Open <http://127.0.0.1:8080/>. The built-in demo pages are served by that same
server:

- <http://127.0.0.1:8080/demo/fixed>
- <http://127.0.0.1:8080/demo/broken>

Choose a built-in page or enter the URL of a page served by the local AccessTrace
server. You can also select multiple source files or a folder as optional context.
These files are supporting material for the selected page; they do not replace
the target URL or get served to the browser.

AccessTrace checks the website first. Only a `BLOCKED` result starts a separate
read-only source review. At that point, supported UTF-8 text files are filtered
for common generated/dependency folders and size limits. Folder selections also
use best-effort `.gitignore` rules; individually selected files bypass those
rules. The matcher supports common glob syntax with fixed limits; if it cannot
safely filter a folder, including when its `.gitignore` is oversized or unreadable
as UTF-8 text, folder-selected files are skipped and reported. Binary, unsupported,
ignored, oversized, and prompt-budget-excluded files are also skipped and reported
with their reasons. Source text is held only for the review request and discarded
on success, timeout, cancellation, or error. Source files are never executed or
changed. The report may retain the review summary, relevant paths, skipped
path/reason metadata, and generated patch. Review the patch before applying it
yourself.

The local-page allowlist and browser sandbox/network restrictions are unchanged.

Choose a built-in demo or load an HTML file, then select **Start assessment**.
The app shows run progress and the live report when the assessment finishes.
AccessTrace invokes the installed Codex CLI with the saved login and validates
each returned keyboard action locally. Planner actions remain limited to
keyboard input and bounded fictional text. The fixed and broken demos support
the goal `Submit the contact form`; leave the goal empty for a whole-site
keyboard assessment. **Sample report** and **Compare demos** show representative
sample data; they do not run browser checks.

Redacted run records are written under `.access-trace/runs/`. The live result
can also be viewed or downloaded from the page. To use a different port, change
`8080` in the command and open that port in the browser.
