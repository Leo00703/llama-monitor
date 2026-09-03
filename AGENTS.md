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
  - `spec/` speculative decoding — one module per draft-model technique
    (`mtp`, `dflash`, `dspark`, `draft_simple`, `eagle3`) + registry
    (`get()`); ngram-* types are flag-only (no module, no drafter/extra
    fields) and are emitted by `flags._ngram_flags`. `spec_type` is a
    comma-separated list (#55): ≤1 draft-model type + any ngram types.
  - `presets.py` preset CRUD (JSON files under `<data-dir>/presets`)
  - `metrics.py` CPU/RAM (psutil), GPU (nvidia-smi), inference metrics
  - `models.py` recursive `.gguf` browser + mmproj detection
  - `proxy.py` `/v1/chat/completions` & `/completion` proxy with settings injection
  - `analytics.py` print_timing parser + SQLite request/energy history
  - `update.py` git self-update (fetch/ff-only pull of origin, version info)
  - `backend_update.py` llama.cpp build updater (release check, download,
    verify, install/rollback, retention)
- `frontend/` — single-page vanilla app: `index.html`, `css/style.css`,
  `js/` (app shell + `pages/`), `fonts/` (bundled Geist Mono woff2),
  `manifest.webmanifest` + `sw.js` + `icons/icon-*.png` (PWA — network-first
  shell cache, live endpoints never cached; optional panel TLS makes LAN/
  tailscale installs possible, see README)
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
  `Feat: <short imperative subject>` / `Docs: <short imperative subject>`.
- One commit per fix; **push after every fix**. Docs updates are separate
  commits, never mixed with code changes.
- Never commit: `TODO.md`, `config.json`, `data/`, `*.log`, `build/`, `dist/`,
  `*.spec`, `.venv/`.
- **Keep `README.md` current**: it describes the product (feature bullets,
  config keys, project layout, commands, tray exe). Re-check it and fix stale
  spots — in a separate `Docs:` commit — whenever a change alters what it
  describes (feature, config key, layout, command, tray/exe behavior) AND at
  least at the end of every work batch, even if the batch was fixes-only. When
  updating, verify each claim against the actual code (grep the module), don't
  just append.

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
  permanent changed (new command, module, convention, or gotcha), and
  re-check `README.md` if the change is user-facing (see Git workflow).

## Verification

- **UI changes**: headless Chrome at **true viewport widths via CDP
  `Emulation.setDeviceMetricsOverride`** (Chrome clamps window width to
  ~500px — see Gotchas). Audit at 390 / 720 / 900 / 1024 / 1440px:
  `document.documentElement.scrollWidth <= width` on every page.
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
- **Frozen startup bootstrap = retried native imports (#64)**: `tray.py` no
  longer imports the native/third-party runtime at module level — `_load_stack()`
  does, with 10 × 2 s retries, because the DLLs it imports live in the freshly
  self-extracted `%TEMP%\_MEI*` folder and a real-time AV scan can lock or
  quarantine them for seconds right after extraction (a top-level import then
  died with a raw `DLL load failed ... _ctypes` traceback — a --noconsole
  build has no console to show it in; the exact report in issue #64). The
  bundle itself is complete: every CI exe ever shipped contains
  `VCRUNTIME140.dll`/`VCRUNTIME140_1.dll`/`libffi-8.dll`/`ucrtbase.dll` +
  `python312.dll`, all Authenticode-valid (Microsoft / Python Software
  Foundation) — so "missing runtime DLL" in the bundle is not the cause,
  AV interference with the extraction is. On persistent failure
  `_bootstrap_failure()` (pure stdlib only — ctypes/PIL are the things that
  broke) writes `llama-monitor-startup-error.log` next to the exe (dev: 
  `startup-error.log` in the data dir) with the traceback + the DLLs actually
  found in `_MEIPASS` + `_PYI_*` env, and shows a detached WinForms dialog via
  `powershell` (skipped for `--smoke`). The message box must stay
  powershell-based — never `ctypes.windll` there (ctypes may be the module
  that failed). CI runs `dist\llama-monitor.exe --smoke` after the build
  (frozen-only breakage the dev smoke can't catch); locally the fresh exe is
  often blocked by Smart App Control (unsigned, by hash) — that's the machine,
  not the build. `requirements-tray.txt` pins `pyinstaller>=6,<7`.
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
- **b10566 slot semantics (tested)**: `-np auto` (default, `-1`) is NOT 1 slot — it starts **4** slots (`n_slots = 4, n_ctx_slot = 8192, kv_unified = 'true'`). With ≥2 slots, 4 concurrent requests run fully parallel (wall/sum ≈ 0.25), also with `--no-cont-batching` (0.29) and `--no-kv-unified`. The **only** config that serializes requests is **1 slot**. The startup log line `load_model: initializing, n_slots = N` (visible in the panel's log view) is the ground truth for what the RUNNING server has; a running server keeps its original flags until restarted (preset edits never auto-restart it).
- **b10566/b10621 KV pool + OOM semantics (verified against source)**: with `--kv-unified`, `n_ctx_seq` = full `-c` (each slot may use the WHOLE pool, dynamic sharing + LCP prefix reuse — server picks slots by prompt similarity), but the pool itself is `-c` tokens **total** (`llama-context.cpp`: `n_ctx_seq = n_ctx` unified vs `n_ctx / n_seq_max` non-unified; `llama-kv-cache.cpp`: K tensor = `n_embd_k × kv_size × n_stream`, `n_stream = 1` unified vs `n_seq_max`). Without unified the pool is the SAME `-c` total, statically split `-c/n_slots` per slot. So **unified vs non-unified costs the same VRAM — switching it off is NOT a memory lever**, it only changes the per-slot cap. What DOES scale with slot count: graph compute buffers (worst-case batch grows with `n_seq_max`) + the MTP draft context (hybrid Qwen3.5/3-Next: plain KV cache of ONLY the nextn layers, pool = target's `n_ctx`, a few hundred MiB — `llama-model.cpp` `mtp_on_hybrid_qwen`). That's why `-np 3/4` OOMs at draft init (~0.5 GB short) while `-np 2` fits, and why the memory levers are `-c` (pool size), MTP off (draft KV + draft buffers), `-b`/`-ub` — NOT `kv_unified`. Consequence: with unified KV the total ACTIVE context across ALL concurrent chats ≤ `-c` tokens (observed: a 78K-token chat then a new chat reusing the slot via LCP).
- **Spec decode does NOT force 1 slot anymore** (verified against b10566 + b10621 source): PR #22838 "parallel drafting" (merged 2026-05-11) reworked the draft context to serve ALL slots in parallel (`common_speculative_init(spec, n_seq)` with `n_seq = n_parallel` in `server-context.cpp`), so `--spec-type draft-mtp -np 4` works on b10xxx+ builds. The panel used to hard-code `-np 1` whenever spec was enabled (stale pre-#22838 assumption, #17) and the presets form locked the slots field to 1 — that silent override was the root cause of the "concurrent chats don't work" report (user preset had MTP + slots 4, panel launched `-np 1`). Removed in `691e32a` (flags.py, presets.js, main.py mismatch-hint). Pre-b10xxx builds may still clamp to 1 slot — the Inference card's orange mismatch hint (`server has N slot · preset wants M`) surfaces that case.
- **Spec types are COMBINABLE — `spec_type` is a comma list (#55, verified against llama.cpp master `common/speculative.cpp` + `docs/speculative.md` + live launches)**: `--spec-type` accepts a comma-separated list of the 11 types (`none`, the 5 draft-model types `draft-simple|draft-eagle3|draft-mtp|draft-dflash|draft-dspark`, and the 5 stateless ngram types `ngram-simple|ngram-map-k|ngram-map-k4v|ngram-mod|ngram-cache`). The parser (`common_speculative_types_from_names`) accumulates all listed types — every one is instantiated. Precedence is a per-seq, per-step FALLBACK CHAIN (`common_speculative_draft`): a FIXED priority order `ngram-simple > ngram-map-k > ngram-map-k4v > ngram-mod > ngram-cache > draft-simple > draft-eagle3 > draft-mtp > draft-dflash > draft-dspark`; the first impl producing a non-empty draft wins that step ("draftless decoding takes precedence"). So ngram types are cheap add-ons tried BEFORE the draft model; ordering in the list is functionally irrelevant. **Multiple draft-model types are structurally invalid** — all of them share ONE draft context (`params.draft.ctx_dft`, loaded once; `draft-mtp` forces `LLAMA_CONTEXT_TYPE_MTP`) — so `schema.SpecSettings` rejects 2+ draft types (the llama.cpp parser does NOT). ngram-only works (the impl list init is NOT gated by `has_spec`; that only gates the draft context). Storage is canonical: draft type first, then ngrams in the priority order (validator normalizes; `none` alone if only none/empty). Panel: `flags._ngram_flags()` emits the per-ngram flags (ngram-simple/map-k/map-k4v: `--spec-ngram-<t>-size-n`/`-size-m`/`-min-hits`; ngram-mod: `--spec-ngram-mod-n-match`/`-n-min`/`-n-max`; ngram-cache: none); draft tokens (`--spec-draft-model`/`-n-max`/`-n-min`/`-p-min`) are emitted ONLY when a draft-model type is present. The old generic `--spec-ngram-size-n/-size-m/-min-hits` are REMOVED deprecated aliases — do not emit them. UI: primary `<select>` (none + 5 draft types) + 5 ngram checkboxes; the comma list is assembled on read (`specTypeFromDOM`) and split on fill (`setSpecTypeUI`). Verified live: `--spec-type ngram-simple,ngram-mod` (230M) and `--spec-type draft-mtp,ngram-simple` (Qwen3.5-0.8B-MTP, `draft acceptance` line present) both run with `speculative:true`.
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
- **DSpark confidence flag is `--spec-draft-p-min`, not `--spec-draft-conf-min`**: the DSpark section of llama.cpp's `docs/speculative.md` still shows the pre-rename name; the current `--help` flag list and `common/speculative.cpp` use `--spec-draft-p-min` (block truncation when the draft's confidence head falls below it; also a generic early-stop for other draft types). Verified against master 2026-08-23. Don't "fix" `dspark.py` back to conf-min.
- **llama.cpp build updater (#18)** — release facts (verified 2026-08, will
  drift): stable tags ship NO binaries — they carry only a `nightly-tag.txt`
  pointer (v0.2.0 → b10566), so "stable" downloads the pinned NIGHTLY zip;
  every `b[NNNN]` nightly is `prerelease: True` and `/releases/latest`
  returns the stable tag. Windows zips are FLAT (`llama-server.exe` at zip
  root). No SHA256/signature artifacts — trust = GitHub TLS + the
  `verify_build()` step. Provenance: `llama-server --version` prints to
  **stderr**; official = `build > 0` AND `commit != "unknown"`; build maps
  1:1 to the `b{N}` tag (that's what makes current-vs-remote comparable).
  `backend_update.py` keeps a 30-min release cache; the panel-side loop
  (`be_loop` in main.py, daemon thread: 25 s startup sleep, 60 s poll) uses
  `check_due()` (≥12 h since last check OR crossed the 00:00/12:00
  boundary) and broadcasts `llama.update.*` via `run_coroutine_threadsafe`
  (never `manager.broadcast` off-thread). All state lives on
  `config.llama_backend` (mutated in place + `save_config`) — restarting
  the panel is the only way to reset `last_check`/`pending` from disk. **Apply is restricted to builds inside
  the storage folder** (`relative_to(storage)`) — rollback to a custom/
  non-managed folder is rejected by design (switch custom builds by editing
  `llama_server_exe`). Retention keeps current + previous MANAGED builds
  (identified by the `llama-monitor.json` manifest); folders without a
  manifest are never deleted. `be_apply` captures `manager.preset_id`
  BEFORE `manager.stop()` (stop clears it). Asset naming is deterministic
  (`llama-b{N}-bin-win-cpu-x64.zip`, `…-vulkan-x64.zip`,
  `…-cuda{ver}-x64.zip`; Linux: `ubuntu-x64.tar.gz` without a "cpu" segment)
  with a prefix-match fallback; `suggest_variant()` reads the nvidia-smi
  driver major (≥580 → cuda-13.3, else cuda-12.4; no nvidia-smi → cpu) and
  only ever SUGGESTS — the user confirms.
- **Headless Chrome** clamps window width to ~500px — set the viewport with
  CDP `Emulation.setDeviceMetricsOverride` per width (works with
  `--headless=new`; verify with `document.documentElement.scrollWidth <= w`).
  In CDP `/json` targets, pick `type === "page"` — `targets[0]` may be a
  chrome-extension background page (symptom: `net::ERR_ABORTED` on navigate,
  empty eval results).
- **Restarting a dev panel**: `pkill -f "uvicorn backend.main"` does NOT
  match (the venv `python.exe` launcher stub re-execs core Python with a
  different command line). Find the real PID via `netstat -ano | grep :PORT`
  and `taskkill //PID <pid> //F` — if the old panel keeps the port, the new
  uvicorn fails to bind SILENTLY and every request (and timing measurement!)
  hits the old code.
- **Headless Chrome CDP + caching**: the persistent profile keeps its disk
  cache between runs — when verifying a JS change, send `Network.enable` +
  `Network.setCacheDisabled` BEFORE navigating, or the page loads the old
  cached script (symptom: `ReferenceError` for a symbol you just added).
- **Inspecting the frozen exe**: `PyInstaller.archive.readers.CArchiveReader`.
  App modules live in the PYZ (`a.open_embedded_archive("PYZ.pyz")`, then
  `pyz.extract("backend.flags")` → code object; list with `pyz.toc`). The
  main script `tray.py` is NOT in the PYZ — it's the CArchive entry named
  `tray` (first TOC entry; `marshal.loads(a.extract("tray"))`). Data files
  are CArchive entries with Windows backslash names (`frontend\index.html`).
  `backend\_buildinfo.json` in the archive carries the built commit sha —
  compare it with `git log` to know which fix the bundled exe contains.
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
- **Shell files must stay cache-coherent after a deploy**: the backend
  serves the frontend through `_CacheAwareStaticFiles` (main.py) —
  html/js/css get `Cache-Control: no-cache` (etag revalidation), everything
  else `public, max-age=1y, immutable`. Without explicit headers Chrome's
  HEURISTIC freshness served the NEW index.html with OLD js/css from the
  disk cache after a deploy (mixed shell: new markup the old scripts don't
  know — the #58 loading screen stranded on screen; the #55 ngram
  checkboxes with no fields). Keep both halves: the SW (sw.js) fetches
  navigations with `cache: "reload"` and subresources with `cache:
  "no-cache"` so the HTTP disk cache can't shadow the network-first path.
  When you change shell files in a way that must invalidate already-cached
  copies in the field, bump the `CACHE` name in sw.js (currently v2) —
  activate() wipes older versions.
- **Self-update = git pull, repo layout is load-bearing**: `update.py` runs
  git in the *repo root* (frozen: exe dir; dev: repo checkout), so updates
  work only when the app runs from a real git checkout with an `origin`
  remote — the bundled exe at the repo root is what makes `git pull` ship
  both code and exe. `apply_update()` is `git merge --ff-only` only and
  refuses local divergence (never rewrites local work); a dirty tree is
  refused too — EXCEPT on the frozen-Windows deployment path, where a dirty
  tree is by definition a leftover from an interrupted update (the deployment
  checkout is never edited by hand) and is auto-recovered with
  `git reset --hard HEAD` (logged, then the ff merge re-applies cleanly).
  "Dirty" = changed TRACKED files only (`_dirty_lines()`), the same in
  `check()` and `apply_update()` — untracked strays can't block a ff-only
  merge, and the error/status list the offending paths.
  **Frozen on Windows the merge is DEFERRED**: a running exe is locked by
  Windows, so `git merge` could never replace `llama-monitor.exe` in-process
  (and every CI refresh ships a new exe). `apply_update()` then fetches,
  writes `<data-dir>/update-bootstrap.ps1` and launches it detached; the
  helper waits for the old PID to die (`Get-Process -Id`) AND until no
  process runs from the exe path and the exe opens exclusively — the
  onefile PARENT (same exe path, not the waited-for PID) keeps the exe image
  mapped until it exits, and merging while it is locked leaves a PARTIAL
  merge (`frontend/*` written, exe not) + a dirty tree (issue #23). The
  helper gives the parent a short (10 s) grace to exit cleanly; if the exe
  is still locked it then looks for exe processes WITHOUT a live child — a
  healthy running instance always has its app child alive and the old app
  child is already gone (PID wait), so only a STUCK bootloader parent
  qualifies (e.g. sitting on the "Failed to remove temporary directory"
  dialog when Windows/Defender won't let it delete its `_MEI*` dir — issue
  #34) and is force-killed; the dialog dies with it and the merge +
  relaunch proceed UNATTENDED (a `note: force-killed …` line is appended to
  `update-result.txt`). A wedged live panel is protected by the same filter
  (its child — or the lingering llama-server — keeps a live child
  relationship), so that case still ends in `RESULT:fail` + skipped merge
  (never a partial merge). The helper then relaunches the app (success OR
  failure — the user always gets a running panel; the lock-timeout path
  skips the relaunch since an instance is still alive).
  `tray.py` removes stale `_MEI*` temp dirs (>24 h) at startup — a
  force-killed parent (or a crash) leaves its ~25 MB extraction dir behind.
  The restart hook is called with `deferred=True` and must NOT spawn
  `--restarting` (the helper is the relauncher). The outcome lands
  in `<data-dir>/update-result.txt` (`pending`, git output, `RESULT:ok` +
  `SHA:` or `RESULT:fail`; no RESULT line = interrupted) and is consumed
  one-shot at next startup via `/api/update/result` → toast. Read it with
  `utf-8-sig` (PowerShell 5.1 `-Encoding utf8` writes a BOM). Dev mode and
  Linux keep the direct in-process merge.
  Restart handoff: `tray.py` registers `set_restart_hook(_restart_app)` in
  `backend.main`; direct updates: the hook spawns the launcher with
  `--restarting` (new process retries the single-instance mutex + waits for
  the old panel's port) and then quits via the normal clean path. Dev/uvicorn
  mode has no hook: the pull succeeds, the restart is reported as manual.
  **Update relaunch keeps the llama-server child running**: `_restart_app`
  calls `set_linger_server()` (backend.process), which makes
  `LlamaServerManager.shutdown()` skip stopping the child — the relaunched
  panel adopts it as an EXTERNAL server, so an in-flight inference survives
  the update AND the old process exits fast (no STOP/KILL_TIMEOUT waits) so
  the bootstrap helper's PID wait stays short. Normal quit (tray menu) does
  NOT linger — the server is stopped as before.
  **Client restart wait = 300 s** (update.js `waitPanelBack`, with live
  elapsed seconds + hint, closable modal): the deferred chain is
  old-exit → helper PID-wait → merge → `Start-Process`, where the relaunched
  onefile exe RE-EXTRACTS its ~25MB bundle on first launch (Windows Defender
  scans it) — commonly 1–3 min, machine-dependent. 120 s timed out this in
  practice (issue #12). Each health probe is abort-bounded (4 s) so a hung
  TCP probe can't eat the budget; the timeout message points at
  `update-result.txt` in the data folder (remote-update diagnosis).
  Version of the running app: frozen builds read
  `_MEIPASS/backend/_buildinfo.json` (CI bakes `GITHUB_SHA`); dev
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
