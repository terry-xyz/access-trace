# AccessTrace

AccessTrace currently has two separate entry points: a static report preview
and a Python journey-and-evidence server. The preview uses representative sample
data and does not start assessments or load records from the server. Connecting
the server's versioned evidence handoff to the report is still integration work.

## Report and comparison preview

The accessible preview provides setup validation, sample reports, and an
original-versus-agent-updated comparison. It does not run a browser assessment.
Comparison slots reuse representative sample evidence; they are not independent
runs, and report values and evidence are labeled as sample data. A configured
goal is shown as entered, but the representative evidence is not evidence about
that goal. The preview accepts only `http://127.0.0.1:4173/` as its target.

From the repository root, serve the static files:

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

Then open <http://127.0.0.1:4173/>.

## Journey and evidence server

The Python server provides the controlled fixed and broken contact-form pages,
assessment endpoints, and redacted run records. Start it from the repository
root:

```sh
python3 -m access_trace --port 8080
```

Open <http://127.0.0.1:8080/>. The controlled targets are:

- <http://127.0.0.1:8080/demo/fixed>
- <http://127.0.0.1:8080/demo/broken>

Create a run with `POST /api/runs` and a JSON body containing `targetUrl`, an
optional `goal`, and optional boolean `simulationMode` (default `true`). A run
without a goal performs a whole-site keyboard assessment; a supplied goal
performs a goal-focused assessment. The returned record is written as redacted
JSON under `.access-trace/runs/` and can be read with `GET /api/runs/<id>`.
For an `IN_PROGRESS` run, `POST /api/runs/<id>/execute` starts a fresh isolated
Chrome session and performs the bounded keyboard journey. The production
planner requires `CODEX_PLANNER_ENDPOINT`, `CODEX_PLANNER_MODEL`, and
`CODEX_PLANNER_API_KEY`; without that configuration, the run ends
inconclusively.

For the supported contact-form goal, the fixed target can complete after
verified keyboard activation. The broken target can be blocked only after
repeated semantic Submit evidence, failed Enter and Space activation, and
relevant recovery. Records retain redacted action and focus evidence, field
character counts and validation metadata, recovery evidence, and a stopping
screenshot reference; they do not retain typed field values or clipboard
contents. Each record exposes an `evidenceHandoff` projection with version
`access-trace.evidence.v1` for downstream report work. Whole-site completion
uses declared controlled-page focus coverage, not the contact form's “Message
sent” confirmation. Unsupported goals remain in the record and finish
inconclusively rather than being reinterpreted.

The report preview and journey server are not connected yet: starting an
assessment through the server does not populate the preview, which continues to
show representative sample data.
