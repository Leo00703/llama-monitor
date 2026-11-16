# Contributing to llama-monitor

Thank you for taking the time to contribute. This project is maintained by a
single maintainer and is developed **with AI agents** — agent-filed issues and
agent-written PRs are normal here. The bar is identical for everyone: **cite
what you verified, and how.**

The single source of truth for repo layout, commands, conventions, and the
hard-won gotchas is [`AGENTS.md`](../AGENTS.md). Read it before a PR — don't
duplicate its rules in comments, just follow them.

## How to help (in order of value per unit of effort)

1. **File a precise issue** — a bug with the checklist below, or an idea in the
   goal / scope shape. A good issue is worth more than a quick PR.
2. **Send a small PR** — bug fixes are very welcome. For a larger feature, open
   an issue first and align on the goal before writing code.
3. **Improve the docs** — stale-claim fixes, screenshots, missing config keys.

For **questions and "how do I…" support**, use
[Discussions](https://github.com/Leo00703/llama-monitor/discussions) instead of
the issue queue.

## Bug reports

Use the [Bug report template](ISSUE_TEMPLATE/bug.yml). A triage-ready report has
all of these:

| Field | Where to find it |
| --- | --- |
| Panel version | Settings → **Current version** (commit sha + date), or `GET /api/update/check` |
| llama-server build | Topbar version label, or `llama-server --version` (e.g. `b10621`) |
| OS | Windows 11 / Ubuntu 24.04 / macOS (Apple Silicon) / … |
| Steps to reproduce | Exact clicks and settings; naming the preset (or listing its fields) is ideal |
| Log excerpt | Copy from the panel log pane — the `[panel] starting: …` line already contains the full launch command; **trim to the failure and scrub secrets, personal paths and hostnames** (see Privacy below) |
| Expected vs actual | One sentence each |

## Feature requests

Use the [Feature request template](ISSUE_TEMPLATE/feature.yml). Keep the same
shape the project uses for its own locked specs:

- **Goal** — one sentence, what the user gets
- **Scope** — what's in, what's explicitly out
- **Open questions** — the decisions to make before coding starts

## Pull requests

- **Small and single-purpose** — one fix or one feature per PR.
- **Commit style** — `Fix: …` / `Feat: …` / `Docs: …`. Docs changes go in
  separate commits, never mixed with code. One commit per fix.
- **Verify before opening** — there is no test framework (by design), so the PR
  description must say exactly what you ran and what you saw:
  - **UI**: headless Chrome at 390 / 720 / 900 / 1024 / 1440 px — set the
    viewport with CDP `Emulation.setDeviceMetricsOverride` (Chrome clamps window
    width to ~500px) and check `document.documentElement.scrollWidth <= <width>`
    on every page (hard rule: no horizontal scroll on mobile).
  - **Backend**: ad-hoc inline Python with synthetic data — state what you checked.
  - **Live E2E**: start the panel, exercise the API, run a real generation.
  - **Frozen builds**: `python tray.py --smoke`.
- **By submitting a PR you agree that your contribution is licensed under the
  [MIT](../LICENSE) license.**

## Deliberate choices — don't "improve" them

Some things in this repo are intentional. The authoritative list lives in
[`AGENTS.md`](../AGENTS.md); in short:

- **No test framework, linter, or CI lint job** — verification is manual / ad-hoc.
- **No frontend framework, build step, or dependencies** — vanilla HTML/CSS/JS.
- **No new Python dependencies** without an issue discussion first.
- **The theme is the official llama.cpp dark design language** — no restyling,
  no Google Fonts / CDN.
- **Windows primary; Linux and macOS must keep working**; `nvidia-smi` is optional.

A PR that "fixes" one of these will be declined — not because it is wrong, but
because it is out of scope.

## Privacy — never introduce user-identifying data

Nothing that identifies a person, machine, or network may enter the repo — not
code, comments, docs, commit messages, screenshots, or log excerpts. Use
placeholders (`C:/llama/llama-server.exe`, `C:/models`, `%APPDATA%\llama-monitor`,
`<your-host>`). See [`AGENTS.md`](../AGENTS.md) → Privacy for the full rule.
