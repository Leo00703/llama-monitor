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
- `frontend/` — single-page vanilla app: `index.html`, `css/style.css`,
  `js/` (app shell + `pages/`)
- `tray.py` — Windows tray launcher (embeds the panel; `--smoke` headless self-test)
- `build_exe.bat` — local PyInstaller build → `dist\llama-monitor-tray.exe`
- `llama-monitor-tray.exe` — latest CI-built tray exe, **tracked at the repo root**
  so `git pull` always ships it (refreshed by CI, see Gotchas)
- `requirements-tray.txt` — tray-only deps (pystray, Pillow, pyinstaller)
- `assets/tray/` — tray mark PNGs + exe icon
- `docs/` — README screenshots (desktop + mobile)
- `.github/workflows/build-exe.yml` — CI: smoke test + PyInstaller + artifact
  upload + commit refreshed exe back to the repo root
- `TODO.md` — local scratchpad, **gitignored, never committed**

## Commands

```bash
python -m venv .venv
pip install -r requirements.txt        # + requirements-tray.txt for the tray launcher
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000   # run the panel
python tray.py                         # tray launcher (Windows); --smoke = headless self-test
build_exe.bat                          # build dist\llama-monitor-tray.exe (Windows)
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
  repo with legacy data next to `llama-monitor-tray.exe` migrates on first
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

- **Any bugfix, new feature, or change the user reports → immediately add it to
  `TODO.md`** as a new item, even in the middle of other work.
- **At every step: check `TODO.md` and update the state of the active task**
  (`[ ]` todo / `[~]` in progress / `[x]` done) with short notes (progress,
  decisions, verification results). Keep it organized at all times.
- `TODO.md` is the session scratchpad: **read it at session start and after any
  compaction, update it after each step**. Never commit it.
- Work through TODO items **in order**; verify each item before moving to the next.
- Verify before committing (see Verification). Ask when a requirement is ambiguous.
- **Future: task tracking moves from `TODO.md` to GitHub Issues**; until then
  `TODO.md` is the single source of truth for open work.

## Context resilience (compaction)

This repo is developed by a **local model (Qwen 3.8 27B Q4_K_S, ~100k context)
in opencode / pi**, where **conversations are compacted mid-work frequently**.
To stay focused on the current work:

- `AGENTS.md` (this file) + `TODO.md` are the durable memory. Keep both current:
  this file holds the stable rules/conventions/gotchas (update it when any of
  those change), `TODO.md` holds the volatile work state.
- **Re-read `TODO.md` (and this file) at the start of a turn or right after a
  compaction, before acting.** The "Next up" section is the map of the current
  work: in-progress item first (state, what is verified, what is pending),
  then pending items in order.
- After finishing an item: mark `[x]` in `TODO.md` with the outcome, commit +
  push, then update this file if anything permanent changed (new command,
  module, convention, or gotcha).

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
- Theme: dark, solid `--bg: #0d0d0d` (official llama.cpp background), **no
  gradients**, blue accent.
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
- **Unsigned exes**: Smart App Control (enforce mode) blocks freshly built exes
  by hash; SmartScreen warns on any unsigned exe. Known environment caveat,
  not a code bug.
- **llama-server logs**: print_timing lines are right-aligned / space-padded in
  current builds — all log-parsing regexes must be whitespace-tolerant. A print
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
  match) — keep that commit subject stable. Each refresh adds a ~25MB object
  to git history (known bloat, revisit later, e.g. GitHub Releases).
- **Config API merges only sent keys**: `POST /api/config` overwrites just
  the fields present in the body — omitted keys keep their current value
  (a full-replace once wiped `active_preset_id` on every Settings save).
  Nested models are still **fully replaced** when their key is sent — a
  client sending `panel` must send both `host` and `port`.
