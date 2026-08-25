## What

One sentence — what this PR changes.

## Why

The issue it fixes (`#…`), or the reason for the change.

## Verified how

There is no test framework in this repo (by design) — say exactly what you ran
and what you saw:

- [ ] **UI**: headless Chrome audit at 390 / 720 / 900 / 1024 / 1440 px —
      `document.scrollWidth == innerWidth` on every page (hard rule: no
      horizontal scroll on mobile)
- [ ] **Backend**: ad-hoc inline Python with synthetic data — what you checked
- [ ] **Live E2E**: panel started, API exercised, a real generation run
      (when the request path is touched)
- [ ] `python tray.py --smoke` (when the frozen build / tray is touched)

Please read [AGENTS.md](../main/AGENTS.md) before contributing — it is the
source of truth for layout, commands, conventions, and hard-won gotchas.

By submitting this PR you agree that your contribution is licensed under the
[MIT](../main/LICENSE) license.
