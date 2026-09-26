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

Web URLs are opened in a fresh isolated browser. With no goal and **Only check
this page** unchecked, AccessTrace scans the selected page and follows same-origin
links up to the page limit beside the URL field. Set `ACCESS_TRACE_MAX_SITE_PAGES` to a
number from 1 to 500 to change the default limit of 25; set it to `0` to crawl
all discovered same-origin pages. Checking **Only check this page** keeps the
scan on the selected URL. Off-site links are not followed.
Uploaded local pages have a stricter network policy and cannot submit forms or
make connections.

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
