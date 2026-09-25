# AccessTrace report preview

This ticket implements the accessible setup and representative whole-site and goal-focused reports. It does not start a browser assessment; every report value and evidence item is sample data and is labeled as such. Entered goals remain free text and appear verbatim in the report, but the representative contact-form sample is not evidence about the entered goal.

Goal-focused setup accepts free-text goals about keyboard interactions and outcomes on the controlled local site. Remote targets, other input modes, security or privacy evaluations, visual checks, requests to override safeguards or run code, and goals without a recognizable keyboard interaction are rejected before a sample report is shown. Accepted text is preserved exactly. The representative contact-form result is sample data, not evidence about the configured goal.

Serve the page from the repository root so its JavaScript modules load:

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

Then open <http://127.0.0.1:4173/>. That exact local URL is the only target accepted by the setup preview.

Run the configuration and score checks with:

```sh
node --test test/assessment.test.mjs
```
