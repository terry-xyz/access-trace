"""Accessible controlled demo pages used by Journey & Evidence."""

from html import escape

from .domain import DEMO_TITLE


def _page_shell(title: str, body: str, script: str = "") -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; background: #f4f6f8; color: #16202a; }}
    main {{ max-width: 42rem; margin: 3rem auto; padding: 2rem; background: white; }}
    label {{ display: block; margin-top: 1rem; font-weight: 650; }}
    input, textarea {{ display: block; width: 100%; box-sizing: border-box; margin-top: .35rem; padding: .65rem; font: inherit; }}
    textarea {{ min-height: 8rem; resize: vertical; }}
    button {{ margin-top: 1.25rem; padding: .7rem 1.1rem; font: inherit; }}
    :focus-visible {{ outline: 3px solid #135dd8; outline-offset: 3px; }}
    [role="status"] {{ margin-top: 1rem; padding: .75rem; background: #e4f6e8; }}
  </style>
</head>
<body>
{body}
{script}
</body>
</html>
""".format(title=title, body=body, script=script)


def demo_page(version: str) -> str:
    title = DEMO_TITLE
    body = """<main data-version="{version}">
  <h1>Fictional contact form</h1>
  <p>This local simulation uses fictional data only.</p>
  <form id="contact-form" aria-describedby="form-help">
    <p id="form-help">Complete the fields and activate Submit with the keyboard.</p>
    <label for="name">Name</label>
    <input id="name" name="name" type="text" autocomplete="off" placeholder="Avery Example" required>
    <label for="email">Email</label>
    <input id="email" name="email" type="email" autocomplete="off" placeholder="avery@example.test" required>
    <label for="message">Message</label>
    <textarea id="message" name="message" autocomplete="off" placeholder="A fictional message" required></textarea>
    <button id="submit" type="submit">Submit</button>
    <p id="success" role="status" aria-live="polite" hidden>Message sent</p>
  </form>
</main>""".format(version=escape(version))

    if version == "fixed":
        script = """<script>
const form = document.getElementById("contact-form");
const success = document.getElementById("success");
form.addEventListener("submit", function (event) {
  event.preventDefault();
  success.hidden = false;
  success.textContent = "Message sent";
});
</script>"""
    else:
        script = """<script>
const form = document.getElementById("contact-form");
const submit = document.getElementById("submit");
form.addEventListener("submit", function (event) {
  event.preventDefault();
});
submit.addEventListener("click", function (event) {
  event.preventDefault();
});
submit.addEventListener("keydown", function (event) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
  }
});
</script>"""

    return _page_shell(title, body, script)


def landing_page(base_url: str) -> str:
    escaped_base_url = escape(base_url, quote=True)
    body = """<main>
  <h1>AccessTrace local assessment</h1>
  <p>Start a fresh, keyboard-only assessment against the controlled local demo.</p>
  <p><a href="{base}/demo/fixed">Open fixed demo</a> · <a href="{base}/demo/broken">Open broken demo</a></p>
  <form id="run-form">
    <label for="target-url">Target URL</label>
    <input id="target-url" name="targetUrl" type="url" value="{base}/demo/fixed" required>
    <label for="goal">Goal (optional)</label>
    <input id="goal" name="goal" type="text" placeholder="Submit the contact form">
    <label><input id="simulation-mode" name="simulationMode" type="checkbox" checked> Simulation mode</label>
    <button type="submit">Start fresh run</button>
  </form>
  <p id="run-status" role="status" aria-live="polite"></p>
</main>""".format(base=escaped_base_url)
    script = """<script>
const form = document.getElementById("run-form");
const status = document.getElementById("run-status");
form.addEventListener("submit", async function (event) {
  event.preventDefault();
  status.textContent = "Starting…";
  const goal = document.getElementById("goal").value;
  const payload = {
    targetUrl: document.getElementById("target-url").value,
    goal: goal || null,
    simulationMode: document.getElementById("simulation-mode").checked
  };
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) {
    status.textContent = result.error.message;
    return;
  }
  if (result.targetVersion !== "fixed" || result.goal !== "Submit the contact form") {
    status.textContent = "Run " + result.id + " started.";
    return;
  }
  status.textContent = "Running keyboard journey…";
  const execution = await fetch("/api/runs/" + result.id + "/execute", {method: "POST"});
  const executed = await execution.json();
  status.textContent = execution.ok
    ? "Run " + executed.id + " " + executed.status.toLowerCase() + "."
    : executed.error.message;
});
</script>"""
    return _page_shell("AccessTrace local assessment", body, script)
