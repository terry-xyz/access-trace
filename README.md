# AccessTrace report preview

This preview implements accessible setup, representative whole-site and goal-focused reports, and an original-versus-agent-updated comparison. The comparison uses one Low-consistency sample result per version. It does not start a browser assessment; every report value and evidence item is sample data and is labeled as such. Entered goals remain free text and appear verbatim, but representative evidence is not evidence about the entered goal.

Goal-focused setup accepts free-text goals describing concrete keyboard interactions with named controls on the controlled local site. Remote targets, other input modes, security or privacy evaluations, visual checks, requests to override safeguards or run code, and goals without a recognizable action on a named control are rejected before a sample report is shown. Accepted text is preserved exactly. The representative contact-form result is sample data, not evidence about the configured goal.

Serve the page from the repository root so its JavaScript modules load:

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

Then open <http://127.0.0.1:4173/>. That exact local URL is the only target accepted by the setup preview.

Run the configuration, score, and comparison checks with:

```sh
node --test
```
