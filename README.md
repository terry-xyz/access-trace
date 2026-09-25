# AccessTrace report preview

This ticket implements the accessible setup and representative whole-site report. It does not start a browser assessment; every report value and evidence item is sample data and is labeled as such.

Serve the page from the repository root so its JavaScript modules load:

```sh
python3 -m http.server 4173 --bind 127.0.0.1
```

Then open <http://127.0.0.1:4173/>. That exact local URL is the only target accepted by the setup preview.

Run the configuration and score checks with:

```sh
node --test test/assessment.test.mjs
```
