# AccessTrace report preview

This preview implements accessible setup, representative whole-site and goal-focused reports, and an original-versus-agent-updated comparison. Comparison consistency defaults to Low (one assessment per version) and can be set to Medium (two) or High (three); both versions always use the same count and settings. It does not start a browser assessment. Repeated slots reuse representative sample evidence and are not independent observations; every report value and evidence item is labeled as sample data. Entered goals remain free text and appear verbatim, but representative evidence is not evidence about the entered goal.

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
