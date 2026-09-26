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

Choose a built-in page or select **Load selected HTML file** to upload one local
standalone `.html` or `.htm` file (UTF-8, up to 1 MiB). Its copied page is served
from the same AccessTrace server; you do not need to start a second web server.
Linked stylesheets, scripts, images, and sibling files are not included. Uploaded
pages support whole-site assessment only; goal-focused runs are reported as
inconclusive because AccessTrace has no trusted success condition for arbitrary
uploaded content.

Uploaded-page browser sessions allow only requests for that exact page URL,
disable DNS prefetch and speculative preconnection, and make the WebRTC peer
connection APIs unavailable before page scripts run. The page is sandboxed, and
the run fails closed if the browser cannot install either lockdown.

Choose a built-in demo or load an HTML file, then select **Start assessment**.
The app shows run progress and the live report when the assessment finishes.
AccessTrace invokes the installed Codex CLI with the saved login and validates
each returned keyboard action locally. Planner actions remain limited to
keyboard input and bounded fictional text. The fixed and broken demos support
the goal `Submit the contact form`; leave the goal empty for a whole-site
keyboard assessment. **Sample report** and **Compare demos** show representative
sample data; they do not run browser checks.

Redacted run records are written under `.access-trace/runs/`; uploaded HTML
copies are kept under `.access-trace/runs/sites/`. The live result can also be
viewed or downloaded from the page. To use a different port, change `8080` in
the command and open that port in the browser.
