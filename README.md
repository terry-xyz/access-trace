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
back with `GET /api/runs/<id>`. For the supported fixed contact-form goal,
`POST /api/runs/<id>/execute` starts a fresh isolated Chrome session, performs
the bounded keyboard journey using the Codex planner, and persists the terminal
result. The durable
record keeps field character counts, validation metadata, and a redacted
stopping screenshot reference, never typed field values or clipboard contents.

The current lifecycle implements the fixed contact-form completion path. Broken
barrier classification, whole-site coverage, failure handling, and report
integration are later work.
