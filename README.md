# AccessTrace controlled local target

This worktree contains the first Journey & Evidence seam: a local controlled
contact form with matching fixed and broken versions, plus a run endpoint that
persists the first bounded observation.

Start it with:

```sh
python3 -m access_trace --port 8080
```

Then open <http://127.0.0.1:8080/>. The controlled targets are:

- <http://127.0.0.1:8080/demo/fixed>
- <http://127.0.0.1:8080/demo/broken>

Start a run with `POST /api/runs` and a JSON body containing `targetUrl`, an
optional `goal`, and optional boolean `simulationMode` (default `true`). The
record is written as redacted JSON under `.access-trace/runs/` and can be read
back with `GET /api/runs/<id>`. A run without a goal performs a whole-site
keyboard assessment; a supplied goal performs a goal-focused assessment. For
the supported contact-form goal,
`POST /api/runs/<id>/execute` starts a fresh isolated Chrome session, performs
the bounded keyboard journey using the Codex planner, and persists the terminal
result. The fixed target can complete after verified keyboard activation; the
broken target can be blocked only after repeated semantic Submit evidence,
failed Enter and Space activation, and relevant recovery. The durable record
keeps field character counts, validation metadata, recovery evidence, and a
redacted stopping screenshot reference, never typed field values or clipboard
contents, and cleanup must be verified. Each record also exposes a versioned
`evidenceHandoff` projection (`access-trace.evidence.v1`) with normalized
assessment settings, ordered actions, focus observations, terminal context,
evidence references, comparison settings, and privacy metadata for downstream
report work.
Whole-site completion requires the declared controlled-page focus coverage to
be complete; it does not use “Message sent” as a universal success signal.
Unsupported goals remain in the record and finish inconclusively rather than
being reinterpreted as the contact-form goal. Delivered keyboard actions that
leave the observed state unchanged are retained as website-action-failure
warnings while the planner continues where possible.
The production planner uses a direct no-tools model request configured with
`CODEX_PLANNER_ENDPOINT`, `CODEX_PLANNER_MODEL`, and
`CODEX_PLANNER_API_KEY`; missing configuration yields an inconclusive run.

The current lifecycle supports whole-site coverage, arbitrary bounded goal
context, and the fixed/broken contact-form success and barrier contrast. The
separate report integration remains later work.
