# Graph Report - llama-monitor  (2026-11-15)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 934 nodes · 1833 edges · 58 communities (44 shown, 14 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 213 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `bd03a77f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Tray launcher & startup
- FastAPI app & endpoints
- Analytics store (SQLite)
- llama-server process manager
- CLI flag translation
- FastAPI imports & request models
- Git self-update & relaunch env
- Config & settings models
- Spec settings & draft validation
- Frontend app shell
- Preset management
- Download, extract & verify
- Release probing & build version info
- Launch preparation routes
- Metrics loop & live inference stats
- Variant & CUDA companion logic
- Ngram params schema
- Settings validation & spec flags
- Server host reachability
- Models page
- Process module & platform helpers
- Service worker
- Backend updater page
- Metrics page
- Analytics page
- Dashboard page
- Generation page
- Presets page
- Settings page
- UI helpers
- Update page
- Docs & contributor conventions
- Implementation Plan (requirements doc)
- Folder browse & path validation
- Spec technique modules & registry
- Backend download & repair flow
- Backend updater loop & check API
- Parallel concurrency diagnostic tool
- Flag argument build & extra flags
- Legacy data migration & data dir
- Model browser scanner
- Proxy request plumbing & analytics writes
- Config persistence & mutation routes
- Frontend API client
- Panel security middleware & proxy core
- Pull request template
- Graphify skill workflow
- CPU sensors & power sampling
- graphify reference: extra exports and benchmark
- llama-server --help parsing
- graphify reference: query, path, explain
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- Model path resolution
- agent/skills/graphify/references/extraction-spec.md

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 83 edges
2. `Gotchas` - 83 edges
3. `LaunchSettings` - 54 edges
4. `LlamaServerManager` - 52 edges
5. `FlagContext` - 34 edges
6. `run_tray()` - 21 edges
7. `AnalyticsStore` - 19 edges
8. `SpecSettings` - 19 edges
9. `AppConfig` - 18 edges
10. `PresetStore` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Repo layout` --references--> `_ngram_flags()`  [INFERRED]
  AGENTS.md → backend/flags.py
- `Gotchas` --references--> `PrintTimingTracker`  [INFERRED]
  AGENTS.md → backend/analytics.py
- `Gotchas` --references--> `LlamaServerManager`  [INFERRED]
  AGENTS.md → backend/process.py
- `Gotchas` --references--> `PanelRequestGuard`  [INFERRED]
  AGENTS.md → backend/main.py
- `Gotchas` --references--> `PanelTokenGate`  [INFERRED]
  AGENTS.md → backend/main.py

## Import Cycles
- None detected.

## Communities (58 total, 14 thin omitted)

### Community 0 - "Tray launcher & startup"
Cohesion: 0.05
Nodes (70): argparse, AppConfig, load_config(), Live configuration, persisted to config.json (machine specific)., Resolve the llama-server executable path (PATH lookup supported)., Load config.json, seeding it from the example file on first run., set_restart_hook(), set_linger_server() (+62 more)

### Community 1 - "FastAPI app & endpoints"
Cohesion: 0.10
Nodes (6): create_app(), analytics_models(), analytics_summary(), analytics_timeseries(), _price(), FastAPI

### Community 2 - "Analytics store (SQLite)"
Cohesion: 0.07
Nodes (27): AnalyticsStore, _avg(), _bucket_bounds(), _bucket_label(), _bucket_next(), _bucket_sequence(), _default_bucket(), _f() (+19 more)

### Community 3 - "llama-server process manager"
Cohesion: 0.05
Nodes (27): Data & config, LlamaServerManager, Any, Owns the llama-server child process and streams its output. State transitions:…, Re-probe the configured exe (e.g. after the build updater swapped it) and…, Stop (if running) and start again. Falls back to last launch args., Remember which preset was used to launch the current server., Port of the active server (panel-started or external), or None. (+19 more)

### Community 4 - "CLI flag translation"
Cohesion: 0.15
Nodes (34): FlagContext, _r_alias(), _r_api_key(), _r_batch(), _r_cache_reuse(), _r_cont_batching(), _r_ctk(), _r_ctv() (+26 more)

### Community 5 - "FastAPI imports & request models"
Cohesion: 0.12
Nodes (25): Application configuration, cross-platform via pathlib. config.json and all…, llama-monitor backend package., FastAPI application: REST API, WebSockets, static frontend serving., GGUF model browser: recursive scan of models_root, mmproj detection (plan 4.6)., Preset CRUD, persisted as JSON files under data/presets/<id>.json., HTTP proxy to the running llama-server (plan 4.7/4.9). Forwards /proxy/*…, Semantic data models: presets, launch settings, speculative decoding. Presets…, copy (+17 more)

### Community 6 - "Git self-update & relaunch env"
Cohesion: 0.12
Nodes (36): AbstractEventLoop, onefile_relaunch_env(), Environment for (re)launching the frozen onefile exe. PyInstaller >= 6.22…, Periodically fetch the git origin and toast about new commits. The interval is…, _update_loop(), apply_update(), check(), _check_now() (+28 more)

### Community 7 - "Config & settings models"
Cohesion: 0.18
Nodes (9): DashboardSettings, LlamaBackendPending, LlamaBackendSettings, PanelSettings, BaseModel, field_validator, A build that is available/downloaded but not yet applied., llama.cpp backend (build) update settings — see backend_update.py. (+1 more)

### Community 8 - "Spec settings & draft validation"
Cohesion: 0.12
Nodes (9): field_validator, The enabled speculator types (empty for "none")., The enabled draft-model type, or None (ngram-only / off)., SpecSettings, Resolver, CLI tokens for this technique (excluding --spec-type itself)., _DFlash, Resolver (+1 more)

### Community 9 - "Frontend app shell"
Cohesion: 0.10
Nodes (31): appendLogLine(), applyState(), autoscrollEl, badge, btnCollapse, btnRestart, btnSidebar, btnStart (+23 more)

### Community 10 - "Preset management"
Cohesion: 0.23
Nodes (7): _now(), PresetStore, Any, Path, (#124) JSON files that exist but cannot be loaded. A preset that fails…, (preset, error): error is None on success, else a short human-readable reason.…, Preset

### Community 11 - "Download, extract & verify"
Cohesion: 0.07
Nodes (31): cleanup_partials(), cuda_lib_patterns(), download_file(), extract_archive(), free_bytes(), _is_panel_download(), local_builds(), missing_cuda_dlls() (+23 more)

### Community 12 - "Release probing & build version info"
Cohesion: 0.09
Nodes (27): BuildInfo, cuda_major_for_driver(), is_valid_tag(), nvidia_driver_version(), parse_devices(), pick_suggested_variant(), probe_gpu(), provenance() (+19 more)

### Community 13 - "Launch preparation routes"
Cohesion: 0.33
Nodes (6): backend_apply(), be_apply(), prepare_launch(), preset_preview(), server_restart(), server_start()

### Community 14 - "Metrics loop & live inference stats"
Cohesion: 0.06
Nodes (35): Gotchas, LiveLogStats, Live tok/s from the server's own progress log lines. These are the server's own…, Server boundary (stop/restart): full reset PLUS the startup flags — they belong…, check_due(), is_valid_variant(), True when a scheduled check is due: last check >12 h old, or a 12 h slot…, Shape check for a stored variant id (cpu / vulkan / cuda-13.4 / openvino-2026.4… (+27 more)

### Community 15 - "Variant & CUDA companion logic"
Cohesion: 0.08
Nodes (36): AsyncClient, _backend_label(), cached_variants(), companion_supported(), fetch_releases(), _fetch_releases_network(), find_asset(), find_companion_asset() (+28 more)

### Community 16 - "Ngram params schema"
Cohesion: 0.40
Nodes (5): NgramLookupSettings, NgramModSettings, BaseModel, ngram-simple / ngram-map-k / ngram-map-k4v params (--spec-ngram-*-size-n,…, ngram-mod params (--spec-ngram-mod-n-match, -n-min, -n-max). Defaults = server…

### Community 17 - "Settings validation & spec flags"
Cohesion: 0.20
Nodes (9): _ngram_flags(), Path, _r_spec(), Per-ngram-type params (issue #55). Emitted when the type is enabled; values…, --spec-type (comma list, #55) plus draft-technique tokens (one module per…, Return (warnings, errors). Errors block the launch, warnings don't., validate_settings(), get() (+1 more)

### Community 18 - "Server host reachability"
Cohesion: 0.50
Nodes (4): loopback_bind(), True when a server bound to `bind` is reachable on 127.0.0.1. (#112)…, Host the panel dials to reach a server bound to `bind` (#112); URL-safe (bare…, server_client_host()

### Community 20 - "Process module & platform helpers"
Cohesion: 0.14
Nodes (20): asyncio, no_window_kwargs(), Spawn kwargs that keep console-app children (llama-server, nvidia-smi, ...)…, nvidia_smi_cached(), Resource and inference metrics collection. - CPU/RAM: psutil - GPU: nvidia-smi…, run_nvidia_smi with the negative result held for GPU_NEGATIVE_TTL., One dict per GPU, or None when nvidia-smi is unavailable/failed., run_nvidia_smi() (+12 more)

### Community 29 - "Settings page"
Cohesion: 0.40
Nodes (4): Browse, PATH_FIELDS, PathHints, Settings

### Community 32 - "Docs & contributor conventions"
Cohesion: 0.06
Nodes (31): Code conventions, Code graph (graphify), Commands, Context resilience (compaction), Deliberate choices — don't "improve" them, Development phases, Git workflow, GitHub Issues (`gh` CLI, authenticated as `Leo00703`) (+23 more)

### Community 33 - "Implementation Plan (requirements doc)"
Cohesion: 0.08
Nodes (24): 1. Ruolo e obiettivo, 2. Contesto hardware (ambiente reale in cui girerà), 3. Stack tecnologico richiesto, 4.10 Analytics e storico, 4.10 Analytics e storico d'uso, 4.11 Stima costo energetico, 4.1 Gestione del processo server, 4.2 Monitoraggio risorse in tempo reale (+16 more)

### Community 34 - "Folder browse & path validation"
Cohesion: 0.14
Nodes (26): browse_directory(), _count_gguf(), _is_dir(), _parent_of(), Any, Path, Filesystem browse + path validation for the settings path pickers (#84). GET…, Validate settings path fields without writing anything. Only keys present in… (+18 more)

### Community 35 - "Spec technique modules & registry"
Cohesion: 0.16
Nodes (10): Base type for speculative decoding techniques (issue #17). One module per…, Technique, DFlash speculative decoding — `draft-dflash`. Block-diffusion draft: the draft…, Classic draft model speculative decoding — `draft-simple`. A much smaller draft…, _DSpark, DSpark speculative decoding — `draft-dspark`. DFlash plus a semi-autoregressive…, EAGLE-3 speculative decoding — `draft-eagle3`. A one-layer draft model reads…, Speculative decoding techniques (issue #17) — one module per technique. The… (+2 more)

### Community 36 - "Backend download & repair flow"
Cohesion: 0.19
Nodes (13): backend_gpu(), backend_repair(), be_download(), fail(), progress(), progress_cuda(), be_repair(), progress() (+5 more)

### Community 37 - "Backend updater loop & check API"
Cohesion: 0.24
Nodes (11): backend_check(), backend_download(), backend_suggest(), backend_versions(), be_current(), be_loop(), be_run_check(), be_target_tag() (+3 more)

### Community 38 - "Parallel concurrency diagnostic tool"
Cohesion: 0.36
Nodes (8): concurrent_futures, auth_headers(), main(), one_request(), open_url(), parallel-test.py — does this llama-server really serve concurrent chats? Fires…, urllib_error, urllib_request

### Community 39 - "Flag argument build & extra flags"
Cohesion: 0.29
Nodes (8): build_args(), _canon_flag(), _flag_name(), _is_flag(), _r_extra(), (#113) Split the extra_flags field. POSIX shlex eats backslashes — a pasted…, Translate semantic settings into CLI argument tokens. `supported` (from…, _split_extra()

### Community 40 - "Legacy data migration & data dir"
Cohesion: 0.20
Nodes (10): default_data_dir(), _is_same_file(), _legacy_root(), migrate_legacy_data(), Path, Merge old in-repo config/data into DATA_DIR (the single source of truth).…, Resolved models root directory, or None if unset., Where in-repo legacy data (config.json, data/) lives. A frozen single-file… (+2 more)

### Community 41 - "Model browser scanner"
Cohesion: 0.27
Nodes (10): models_list(), _iter_files(), walk(), list_models(), Any, Path, List every .gguf file under `root` (mmproj files excluded from the list itself…, Depth-first walk of `root`, skipping hidden entries (dot-prefixed files and… (+2 more)

### Community 42 - "Proxy request plumbing & analytics writes"
Cohesion: 0.22
Nodes (10): _complete_request(), llama_proxy(), _model_for_request(), _record_failure(), _submit_db_write(), _done(), _warn_key_withheld(), _is_loopback_host() (+2 more)

### Community 44 - "Config persistence & mutation routes"
Cohesion: 0.29
Nodes (7): Atomically persist the configuration to config.json. (#111) Callers span the…, save_config(), backend_set_config(), post_config(), presets_activate(), presets_create(), presets_delete()

### Community 45 - "Frontend API client"
Cohesion: 0.48
Nodes (6): API, authHeaders(), panelToken(), parseBody(), request(), unauthorizedError()

### Community 49 - "Panel security middleware & proxy core"
Cohesion: 0.11
Nodes (13): get_config(), _host_without_port(), PanelRequestGuard, PanelTokenGate, _protected_path(), Surface slow requests in the panel's own log view (#77). The log card is the…, Optional shared-secret panel auth (#92). Enforced only while `panel.token` is…, The endpoints both panel guards (token #92, host/origin #93) cover. (+5 more)

### Community 51 - "Pull request template"
Cohesion: 0.50
Nodes (3): Verified how, What, Why

### Community 54 - "Graphify skill workflow"
Cohesion: 0.06
Nodes (27): PowerSampler, Ring buffer of (ts, total_power_w) samples; estimates Wh over a window.…, Average power in [start, end] x duration, in Wh. None if no samples., For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify (+19 more)

### Community 55 - "CPU sensors & power sampling"
Cohesion: 0.22
Nodes (5): CpuSensors, CPU package temperature + power from sysfs (Linux only). Windows exposes…, Hottest CPU package zone in °C, or None when no zone is exposed., Package power in watts (RAPL energy delta, or AMD hwmon average)., `get_auth` returns headers (Authorization) for the llama-server polls — the…

### Community 58 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 62 - "llama-server --help parsing"
Cohesion: 0.33
Nodes (6): parse_help(), _parse_help_output(), (documented flag names, documented --spec-type values) from --help., Run `llama-server --help`. Returns (documented flag names, documented --spec-…, _warm_help(), spec_types()

### Community 64 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 71 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 72 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 73 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

## Knowledge Gaps
- **121 isolated node(s):** `Models`, `SHELL`, `Backend`, `Metrics`, `Analytics` (+116 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 405 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Gotchas` connect `Metrics loop & live inference stats` to `Tray launcher & startup`, `FastAPI app & endpoints`, `Analytics store (SQLite)`, `llama-server process manager`, `Git self-update & relaunch env`, `Spec settings & draft validation`, `Frontend app shell`, `Download, extract & verify`, `Release probing & build version info`, `Launch preparation routes`, `Variant & CUDA companion logic`, `Settings validation & spec flags`, `Process module & platform helpers`, `Docs & contributor conventions`, `Folder browse & path validation`, `Backend download & repair flow`, `Backend updater loop & check API`, `Proxy request plumbing & analytics writes`, `Config persistence & mutation routes`, `Frontend API client`, `Panel security middleware & proxy core`?**
  _High betweenness centrality (0.301) - this node is a cross-community bridge._
- **Why does `create_app()` connect `FastAPI app & endpoints` to `Tray launcher & startup`, `Analytics store (SQLite)`, `llama-server process manager`, `CLI flag translation`, `FastAPI imports & request models`, `Config & settings models`, `Preset management`, `Launch preparation routes`, `Metrics loop & live inference stats`, `Settings validation & spec flags`, `Folder browse & path validation`, `Backend download & repair flow`, `Backend updater loop & check API`, `Flag argument build & extra flags`, `Model browser scanner`, `Proxy request plumbing & analytics writes`, `Config persistence & mutation routes`, `Panel security middleware & proxy core`, `Graphify skill workflow`, `llama-server --help parsing`?**
  _High betweenness centrality (0.168) - this node is a cross-community bridge._
- **Why does `LlamaServerManager` connect `llama-server process manager` to `FastAPI app & endpoints`, `FastAPI imports & request models`, `Git self-update & relaunch env`, `Metrics loop & live inference stats`, `Process module & platform helpers`?**
  _High betweenness centrality (0.115) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `create_app()` (e.g. with `Gotchas` and `AppConfig`) actually correct?**
  _`create_app()` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 82 inferred relationships involving `Gotchas` (e.g. with `_bucket_bounds()` and `_bucket_next()`) actually correct?**
  _`Gotchas` has 82 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `LaunchSettings` (e.g. with `build_args()` and `_r_alias()`) actually correct?**
  _`LaunchSettings` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `LlamaServerManager` (e.g. with `Gotchas` and `_metrics_loop()`) actually correct?**
  _`LlamaServerManager` has 3 INFERRED edges - model-reasoned connections that need verification._