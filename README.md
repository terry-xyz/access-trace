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
back with `GET /api/runs/<id>`.

This ticket stops at the fresh run and first observation. Journey planning,
keyboard execution, terminal classification, and report integration are later
work.
