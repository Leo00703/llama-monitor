# AGENTS.md

Guidance for AI agents (and humans) working in this repo.

## Project

llama-monitor: a lightweight web control panel for a local `llama-server`
(llama.cpp) instance. Stack: FastAPI backend + vanilla HTML/CSS/JS frontend
(**no build step, no frontend dependencies**) + a Windows system-tray launcher
(`tray.py`). `Implementation Plan.md` is the requirements source of truth.

## Repo layout

- `backend/` — FastAPI app + logic modules:
  - `main.py` REST API, WebSockets, static frontend
  - `config.py` config load/save + user-data-dir resolution & legacy migration
  - `schema.py` Pydantic models (launch settings, API payloads)
  - `process.py` llama-server child-process manager (state machine, log capture)
  - `flags.py` semantic settings → CLI flags translation + `--help` validation
  - `presets.py` preset CRUD (JSON files under `<data-dir>/presets`)
  - `metrics.py` CPU/RAM (psutil), GPU (nvidia-smi), inference metrics
  - `models.py` recursive `.gguf` browser + mmproj detection
  - `proxy.py` `/v1/chat/completions` & `/completion` proxy with settings injection
  - `analytics.py` print_timing parser + SQLite request/energy history
  - `update.py` git self-update (fetch/ff-only pull of origin, version info)
- `frontend/` — single-page vanilla app: `index.html`, `css/style.css`,
  `js/` (app shell + `pages/`), `fonts/` (bundled Geist Mono woff2)
- `tray.py` — Windows tray launcher (embeds the panel; `--smoke` headless
  self-test; `--restarting` internal flag for the update relaunch handoff)
- `build_exe.bat` — local PyInstaller build → `dist\llama-monitor.exe`
- `llama-monitor.exe` — latest CI-built tray exe, **tracked at the repo root**
  so `git pull` always ships it (refreshed by CI, see Gotchas)
- `requirements-tray.txt` — tray-only deps (pystray, Pillow, pyinstaller)
- `assets/tray/` — tray mark PNGs + exe icon
- `docs/` — README screenshots (desktop + mobile)
- `.github/workflows/build-exe.yml` — CI: smoke test + bake
  `backend/_buildinfo.json` (commit + date, gitignored) + PyInstaller +
  artifact upload + commit refreshed exe back to the repo root

## Commands

```bash
python -m venv .venv
pip install -r requirements.txt        # + requirements-tray.txt for the tray launcher
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000   # run the panel
python tray.py                         # tray launcher (Windows); --smoke = headless self-test
build_exe.bat                          # build dist\llama-monitor.exe (Windows)
```

There is **no test framework, linter, or formatter** configured. Verification is
manual/ad-hoc (see Verification below).

## Data & config

- All persistent data (config, presets, analytics DB) lives **outside the repo**:
  `%APPDATA%\llama-monitor` (Windows), `~/.config/llama-monitor` (Linux/macOS);
  override with the `LLAMA_MONITOR_DATA` env var.
- Never write config/data into the working tree. In-repo `config.json` and
  `data/` are gitignored legacy, auto-migrated **merge-based** on startup
  (destination wins name collisions; conflicting files are kept + warned,
  never deleted). Frozen builds resolve the legacy root from the **exe's own
  folder** (PyInstaller onefile `__file__` points at `_MEIPASS`), so a pulled
  repo with legacy data next to `llama-monitor.exe` migrates on first
  start.
- `config.example.json` is the source of truth for config keys.
- The panel only manages `llama-server` processes it started itself; a server
  already running on the port is treated as **external**.

## Git workflow

- Branch `main`. Commit style: `Fix: <short imperative subject>` /
  `Feat: <short imperative subject>`.
- One commit per fix; **push after every fix**.
- Never commit: `TODO.md`, `config.json`, `data/`, `*.log`, `build/`, `dist/`,
  `*.spec`, `.venv/`.

## Working with the user (task tracking)

- **Open work is tracked in GitHub Issues, not a local file.** The old
  `TODO.md` local scratchpad is **retired** (still gitignored — do not
  recreate or commit it).
- **Any bugfix, new feature, or change the user reports → immediately create a
  GitHub Issue**, even in the middle of other work.
- **At session start (and after any compaction): `gh issue list` and work
  through the open Issues in order** (lowest number first, unless the user
  re-prioritizes). Verify each item before closing it.
- **Close the Issue when done** with a short comment recording the outcome
  (commit sha + verification). Add progress/decision notes as Issue comments
  while working.
- Verify before committing (see Verification). Ask when a requirement is
  ambiguous.

### GitHub Issues (`gh` CLI, authenticated as `Leo00703`)

```bash
gh issue list                                   # the open work queue
gh issue list --json number,title,labels        # compact queue view
gh issue view <n>                               # full body of one issue
gh issue create --title "..." --body-file f.md --label bug   # new work item
gh issue close <n> --comment "done: <sha> — verified ..."    # finish an item
gh issue edit <n> --label enhancement           # relabel
```

Labels: `bug` (defect, incl. minor/edge-case findings) and `enhancement`
(feature / optimization / cross-platform gap). The grouped "Backlog / future
ideas" issue holds the out-of-scope plan §7 items.

## Context resilience (compaction)

This repo is developed by a **local model (Qwen 3.8 27B Q4_K_S, ~100k context)
in opencode / pi**, where **conversations are compacted mid-work frequently**.
To stay focused on the current work:

- `AGENTS.md` (this file) + **the open GitHub Issues** are the durable
  memory. This file holds the stable rules/conventions/gotchas (update it
  when any of those change); the open Issues hold the volatile work queue.
- **Re-read this file and `gh issue list` at the start of a turn or right
  after a compaction, before acting.** The open Issues (lowest number first)
  are the map of the current work.
- After finishing an item: commit + push, close the Issue with a short
  outcome comment (sha + verification), then update this file if anything
  permanent changed (new command, module, convention, or gotcha).

## Verification

- **UI changes**: headless Chrome at **true viewport widths via an iframe
  harness** (Chrome clamps window width to ~500px — see Gotchas). Audit at
  390 / 720 / 900 / 1024 / 1440px: `document.scrollWidth == innerWidth` on
  every page.
- **Hard rule: never horizontal scroll on mobile**; topbar stays static (only
  `main` scrolls, with safe-area bottom padding).
- **Live E2E**: start the panel on :8000 and exercise the API
  (`/api/health`, config save round-trip, a real generation through the proxy).
- **Backend logic**: ad-hoc inline Python scripts with synthetic data
  (no framework).
- **Frozen builds**: `python tray.py --smoke` (headless self-test used by CI).

## Code conventions

- Frontend: vanilla HTML/CSS/JS, no framework, no build step; follow the
  existing patterns in `frontend/js/pages/`.
- Python: `pathlib` everywhere, no hardcoded absolute paths; stay
  cross-platform (Windows primary, Linux must keep working; `nvidia-smi` is
  optional — GPU cards are hidden when absent).
- Theme: **official llama.cpp dark design language** — solid `--bg: #0d0d0d`,
  brand-orange accent `#f65e00` (not #ff6467 — that's the official *error*
  color), semantics ok `#00bc7d` / warn `#fe9a00` / err `#ff6467` / info
  `#ad46ff`, cards `rgba(38,38,38,.75)` + backdrop blur, pill buttons, **no
  gradients** (the `<select>` chevron arrows are the one sanctioned
  gradient). Font: system sans stack + bundled **Geist Mono**
  (`frontend/fonts/geist-mono-latin.woff2`, variable 400–600) for logs/code/
  metrics — do not add a Google Fonts CDN dependency.
- Comments: minimal; add a comment only for a non-obvious "why".

## Gotchas

- **Python 3.14 + PyInstaller**: `import pyinstaller` (lowercase) fails without
  `PYTHONCASEOK=1` (case-insensitive-import quirk). It is set in `build_exe.bat`
  and the CI workflow — keep it there.
- **pystray 0.19.x API**: there is **no `icon.update()`**. Use
  `icon.icon = <PIL image>`, `icon.title = <text>`, `icon.update_menu()`.
  Dynamic menus: `pystray.Menu(callable_factory)`.
- **Uvicorn in a daemon thread**: shut down via `server.should_exit = True` →
  `thread.join(...)` → `server.force_exit = True`. In a `--noconsole` frozen
  build `sys.stdout`/`sys.stderr` are `None`; uvicorn's default logging config
  (`ext://sys.stderr`) then raises `ValueError: Unable to configure formatter`
  and the panel thread dies silently (health never comes up). Redirect both
  streams to `os.devnull` before starting uvicorn
  (see `_install_stdout_stderr()` in `tray.py`).
- **PyInstaller flags** (see `build_exe.bat`): `--onefile --noconsole`,
  `--add-data "frontend;frontend"` (Windows path separator), `--icon
  assets\tray\icon.ico`, plus `--hidden-import` for uvicorn's auto-imported
  modules (`uvicorn.loops.auto`, `uvicorn.loops.asyncio`,
  `uvicorn.protocols.http.auto`, `uvicorn.protocols.http.h11_impl`,
  `uvicorn.protocols.websockets.auto`, `uvicorn.protocols.websockets.wsproto_impl`,
  `uvicorn.protocols.websockets.websockets_impl`, `websockets`, `wsproto`,
  `six`, `pystray._win32`).
- **PyInstaller ≥ 6.22 onefile relaunch = environment poisoning**: an onefile
  exe determines its process role *solely* from inherited env vars
  (`_PYI_ARCHIVE_FILE`, `_PYI_PARENT_PROCESS_LEVEL`, `_PYI_APPLICATION_HOME_DIR`).
  A relaunched exe (e.g. the updater's bootstrap `Start-Process`, or
  `tray.py`'s `Popen([sys.executable, ...])`) inherits the running app's
  `_PYI_*` vars, takes the CHILD path, and 6.22+ then validates that the
  parent process runs the same executable — parent is powershell.exe, so it
  dies with the modal "Security validation failure: parent process has
  different executable!" dialog (issue #11). Fix: every relaunch point must
  use `onefile_relaunch_env()` (config.py) — environment minus all `_PYI_*`
  plus the documented `PYINSTALLER_RESET_ENVIRONMENT=1` escape hatch (the
  generated bootstrap ps1 repeats both before `Start-Process` as
  defense-in-depth). Do NOT "fix" by pinning PyInstaller: the validation is
  legitimate, the inherited role vars are the bug.
- **Unsigned exes**: Smart App Control (enforce mode) blocks freshly built exes
  by hash; SmartScreen warns on any unsigned exe. Known environment caveat,
  not a code bug.
- **llama-server logs**: print_timing lines are right-aligned / space-padded in
  current builds — all log-parsing regexes must be whitespace-tolerant.
- **Live tok/s: prefer the server's own log lines, not /metrics.** Recent
  llama.cpp updates its `/metrics` token counters only when a request
  completes (per-request, not live), so 1.5s counter deltas read 0 for the
  whole generation. Newer builds (b10xxx) also print live progress to the
  log — `prompt processing, ... N tokens per second` (~1/s during prompt) and
  `n_gen = N, tg = X t/s, tg_3s = Y t/s` (~3/s during generation). `LiveLogStats`
  (analytics.py) parses those and `_enrich_inference` (main.py) uses them as
  the PRIMARY live source while a slot is busy (fresh = ≤10s, per-phase),
  falling back to `/slots` per-slot progress deltas (`next_token.n_decoded`,
  `n_prompt_tokens`, see `MetricsCollector._inference()`), then to the
  counter deltas for older builds / external servers. NOTE: llama.cpp changes
  the `/slots` and `/metrics` JSON between builds, so the log lines are the
  most build-proof live source; keep the /slots + counter fallbacks.
  A print
  timing block is several `print_timing` lines (prompt/eval/total, and for
  spec-decode a `draft acceptance` line); newer builds insert extra
  `print_timing` continuation lines (e.g. `graphs reused = N`) inside the
  block. The tracker must therefore treat the block as open until a
  NON-`print_timing` line arrives — finalizing on the `total` line (or any
  single line) silently drops the later `draft acceptance` line.
- **Headless Chrome** clamps window width to ~500px — size the viewport with an
  iframe inside the page, not with the browser window.
- **CI commits the exe back to `main`**: `build-exe.yml` pushes the built exe
  to the repo root as bot commit `"Build: refresh bundled tray exe"` (sha256
  skip when unchanged). Loop prevention = the workflow skips the whole build
  when the triggering push's HEAD is that exact bot commit (author + subject
  match) — keep that commit subject stable. Observed 2026-08-19: GitHub does
  NOT trigger a new run for the bot's own push (no run is ever registered
  for a bot commit), so the skip step is defensive and the loop ends after
  one bot commit. PyInstaller output is slightly non-deterministic between
  runner runs (a few hundred bytes), so even doc-only pushes can produce a
  refresh commit. Each refresh adds a ~25MB object to git history (known
  bloat, revisit later, e.g. GitHub Releases).
- **Config API merges only sent keys**: `POST /api/config` overwrites just
  the fields present in the body — omitted keys keep their current value
  (a full-replace once wiped `active_preset_id` on every Settings save).
  Nested models are still **fully replaced** when their key is sent — a
  client sending `panel` must send both `host` and `port`.
- **Self-update = git pull, repo layout is load-bearing**: `update.py` runs
  git in the *repo root* (frozen: exe dir; dev: repo checkout), so updates
  work only when the app runs from a real git checkout with an `origin`
  remote — the bundled exe at the repo root is what makes `git pull` ship
  both code and exe. `apply_update()` is `git merge --ff-only` only and
  refuses a dirty tree or local divergence (never rewrites local work).
  "Dirty" = changed TRACKED files only (`_dirty_lines()`), the same in
  `check()` and `apply_update()` — untracked strays can't block a ff-only
  merge, and the error/status list the offending paths.
  **Frozen on Windows the merge is DEFERRED**: a running exe is locked by
  Windows, so `git merge` could never replace `llama-monitor.exe` in-process
  (and every CI refresh ships a new exe). `apply_update()` then fetches,
  writes `<data-dir>/update-bootstrap.ps1` and launches it detached; the
  helper waits for the old PID to die (`Get-Process -Id`), merges, and
  relaunches the app itself (success OR failure — the user always gets a
  running panel). The restart hook is called with `deferred=True` and must
  NOT spawn `--restarting` (the helper is the relauncher). The outcome lands
  in `<data-dir>/update-result.txt` (`pending`, git output, `RESULT:ok` +
  `SHA:` or `RESULT:fail`; no RESULT line = interrupted) and is consumed
  one-shot at next startup via `/api/update/result` → toast. Read it with
  `utf-8-sig` (PowerShell 5.1 `-Encoding utf8` writes a BOM). Dev mode and
  Linux keep the direct in-process merge.
  Restart handoff: `tray.py` registers `set_restart_hook(_restart_app)` in
  `backend.main`; direct updates: the hook spawns the launcher with
  `--restarting` (new process retries the single-instance mutex + waits for
  the old panel's port) and then quits via the normal clean path (lifespan
  stops llama-server). Dev/uvicorn mode has no hook: the pull succeeds, the
  restart is reported as manual. Version of the running app: frozen builds
  read `_MEIPASS/backend/_buildinfo.json` (CI bakes `GITHUB_SHA`); dev
  reports live `git HEAD`.
- **Detached helper processes on Windows**: `tasklist`/`timeout` silently
  kill a console-less detached `cmd /c` (empirically) — use a PowerShell
  script instead (`powershell -NoProfile -ExecutionPolicy Bypass -File
  x.ps1`); `Get-Process`, `Start-Sleep`, `git`, `Start-Process` all work
  detached. `DETACHED_PROCESS` (0x8) makes powershell.exe die at startup
  with rc 0 and no output — launch with `CREATE_NO_WINDOW |
  CREATE_NEW_PROCESS_GROUP` + devnull stdout/stderr only. `Start-Process`
  takes `-FilePath` (there is no `-LiteralPath`). PID 0 is the system idle
  process (always alive) — never use it as a "dead PID" in tests.
- **Update-checker thread**: `create_app()`'s lifespan starts a daemon
  thread (`_update_loop`) that polls `update_check_minutes` (live config,
  0 = off) and broadcasts `update.available` over WS via
  `loop.call_soon_threadsafe(manager.broadcast, ...)` — never call
  `manager.broadcast` from another thread directly (asyncio.Queue is not
  thread-safe). The frontend toast dedupes by the latest commit sha; a
  dismissed sha stays dismissed until a newer commit arrives.
