# AccessTrace report preview

This ticket implements the accessible setup and representative whole-site and goal-focused reports. It does not start a browser assessment; every report value and evidence item is sample data and is labeled as such. Entered goals are shown in the report, but the representative goal sample may not match the entered goal.

Goals are limited to keyboard assessment of the controlled local demo. Remote URLs, non-keyboard interaction modes, non-keyboard criteria such as color contrast and alternative text, full-conformance requests, and requests to override safeguards or run code are rejected before a sample report is shown.

Serve the page from the repository root so its JavaScript modules load:

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

Then open <http://127.0.0.1:4173/>. That exact local URL is the only target accepted by the setup preview.

Run the configuration and score checks with:

```sh
node --test test/assessment.test.mjs
```
