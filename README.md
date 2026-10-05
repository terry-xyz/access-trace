# AccessTrace

AccessTrace assesses keyboard accessibility on web pages and uploaded local sites.
It records browser actions and focus, reviews the evidence with Codex, and suggests
source fixes for approval. Results are not a full accessibility or WCAG conformance audit.

[Try the interactive demo](https://terry-xyz.github.io/access-trace/). It uses clearly
labeled illustrative results; live assessments require the local app below.

## Run AccessTrace

Requirements: Python 3.9+, Google Chrome or Chromium, and the Codex CLI signed in
with `codex login`. Browser discovery supports macOS and Linux; on Linux, install
Chrome or Chromium on `PATH`, or Chromium through Flatpak. No Python packages or
OpenAI API key are required.

From the repository root:

```sh
python -m access_trace --port 8080
```

Open <http://127.0.0.1:8080/>, enter an HTTP/HTTPS URL or choose an HTML file and its
supporting assets, then select **Start assessment**.

- Leave the goal blank to scan same-origin pages, or enter a goal for a focused run.
- Use **Only check this page** to stay on the selected URL. The page limit defaults
  to 25; `0` scans all discovered pages. `ACCESS_TRACE_MAX_SITE_PAGES` changes the default.
- Uploaded pages run in a sandbox that blocks external requests and form submissions.
- In the report, choose source files and select **Fix** to propose a patch. Review it
  before **Approve and apply**, or download it if browser file writes are unavailable.

Redacted records are saved in `.access-trace/runs/` and can be downloaded from the
report. Use `--run-directory` to change their location.

Run the checks (Node.js 18+ is needed for JavaScript tests):

```sh
python -m unittest discover -s tests
node --test
```
