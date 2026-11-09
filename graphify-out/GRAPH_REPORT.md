# Graph Report - llama-monitor  (2026-11-09)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 827 nodes · 1710 edges · 42 communities (25 shown, 17 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 225 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ae66b487`
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
- Spawn & probe helpers
- Speculative decoding techniques
- Frontend app shell
- Preset management
- Build install & retention
- Variant & CUDA logic
- Release asset parsing
- Panel security middleware & proxy core
- Release asset discovery
- Release fetching
- Backend update API & progress
- Download, extract & verify
- Models page
- GPU probing
- Service worker
- API client
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
- Flags build & validation
- Model browser scanner
- Proxy analytics plumbing
- Slow request logging middleware
- Ngram params schema
- Pull request template

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 86 edges
2. `Gotchas` - 80 edges
3. `LaunchSettings` - 56 edges
4. `LlamaServerManager` - 47 edges
5. `FlagContext` - 36 edges
6. `run_tray()` - 20 edges
7. `AnalyticsStore` - 19 edges
8. `SpecSettings` - 19 edges
9. `AppConfig` - 18 edges
10. `_metrics_loop()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Repo layout` --references--> `_ngram_flags()`  [INFERRED]
  AGENTS.md → backend/flags.py
- `Gotchas` --references--> `LiveLogStats`  [INFERRED]
  AGENTS.md → backend/analytics.py
- `Gotchas` --references--> `PrintTimingTracker`  [INFERRED]
  AGENTS.md → backend/analytics.py
- `Gotchas` --references--> `LlamaServerManager`  [INFERRED]
  AGENTS.md → backend/process.py
- `Gotchas` --references--> `PanelRequestGuard`  [INFERRED]
  AGENTS.md → backend/main.py

## Import Cycles
- None detected.

## Communities (42 total, 17 thin omitted)

### Community 0 - "Tray launcher & startup"
Cohesion: 0.07
Nodes (37): AppConfig, load_config(), set_restart_hook(), set_linger_server(), acquire_single_instance(), apply_state(), _bootstrap_failure(), _cleanup_stale_mei_dirs() (+29 more)

### Community 1 - "FastAPI app & endpoints"
Cohesion: 0.05
Nodes (49): save_config(), parse_help(), create_app(), analytics_models(), analytics_summary(), analytics_timeseries(), api_validate_paths(), backend_apply() (+41 more)

### Community 2 - "Analytics store (SQLite)"
Cohesion: 0.05
Nodes (14): AnalyticsStore, _avg(), _bucket_bounds(), _bucket_label(), _bucket_next(), _bucket_sequence(), _default_bucket(), _f() (+6 more)

### Community 3 - "llama-server process manager"
Cohesion: 0.06
Nodes (3): Data & config, spawn_argv(), LlamaServerManager

### Community 4 - "CLI flag translation"
Cohesion: 0.14
Nodes (34): FlagContext, _r_alias(), _r_api_key(), _r_batch(), _r_cache_reuse(), _r_cont_batching(), _r_ctk(), _r_ctv() (+26 more)

### Community 5 - "FastAPI imports & request models"
Cohesion: 0.10
Nodes (3): _model_from_args(), PresetRequest, StartRequest

### Community 6 - "Git self-update & relaunch env"
Cohesion: 0.10
Nodes (21): no_window_kwargs(), onefile_relaunch_env(), apply_update(), check(), _check_now(), consume_update_result(), current_version(), _dirty_lines() (+13 more)

### Community 7 - "Spawn & probe helpers"
Cohesion: 0.07
Nodes (10): _parse_help_output(), CpuSensors, _find_any(), MetricsCollector, nvidia_smi_cached(), parse_prometheus(), run_nvidia_smi(), _to_float() (+2 more)

### Community 9 - "Frontend app shell"
Cohesion: 0.10
Nodes (31): appendLogLine(), applyState(), autoscrollEl, badge, btnCollapse, btnRestart, btnSidebar, btnStart (+23 more)

### Community 10 - "Preset management"
Cohesion: 0.30
Nodes (3): _now(), PresetStore, Preset

### Community 11 - "Build install & retention"
Cohesion: 0.12
Nodes (11): extract_archive(), free_bytes(), local_builds(), panel_download_path(), prune(), read_manifest(), record_cuda_runtime(), resolve_storage() (+3 more)

### Community 12 - "Variant & CUDA logic"
Cohesion: 0.15
Nodes (6): cleanup_partials(), cuda_major_for_driver(), _is_panel_download(), is_valid_tag(), pick_suggested_variant(), _ver_tuple()

### Community 13 - "Release asset parsing"
Cohesion: 0.22
Nodes (6): _backend_label(), parse_build_asset(), parse_cudart_asset(), _parse_rest(), provenance(), _variant_id()

### Community 14 - "Panel security middleware & proxy core"
Cohesion: 0.08
Nodes (13): Gotchas, check_due(), is_valid_variant(), _CacheAwareStaticFiles, _update_loop(), ProxyOffline, ServerProxy, body_iter() (+5 more)

### Community 15 - "Release asset discovery"
Cohesion: 0.14
Nodes (10): cached_variants(), companion_supported(), find_asset(), find_companion_asset(), local_arch(), local_platform(), nvidia_driver_version(), release_assets() (+2 more)

### Community 16 - "Release fetching"
Cohesion: 0.29
Nodes (5): fetch_releases(), _fetch_releases_network(), _kick_background_refresh(), _bg(), _spawn()

### Community 29 - "Settings page"
Cohesion: 0.40
Nodes (4): Browse, PATH_FIELDS, PathHints, Settings

### Community 32 - "Docs & contributor conventions"
Cohesion: 0.06
Nodes (31): Code conventions, Code graph (graphify), Commands, Context resilience (compaction), Deliberate choices — don't "improve" them, Development phases, Git workflow, GitHub Issues (`gh` CLI, authenticated as `Leo00703`) (+23 more)

### Community 33 - "Implementation Plan (requirements doc)"
Cohesion: 0.08
Nodes (25): 1. Ruolo e obiettivo, 2. Contesto hardware (ambiente reale in cui girerà), 3. Stack tecnologico richiesto, 4.10 Analytics e storico, 4.10 Analytics e storico d'uso, 4.11 Stima costo energetico, 4.1 Gestione del processo server, 4.2 Monitoraggio risorse in tempo reale (+17 more)

### Community 34 - "Folder browse & path validation"
Cohesion: 0.06
Nodes (24): BuildInfo, run_version(), browse_directory(), _count_gguf(), _is_dir(), _parent_of(), _res(), _start_dir() (+16 more)

### Community 35 - "Spec technique modules & registry"
Cohesion: 0.15
Nodes (3): Technique, _DFlash, get()

### Community 39 - "Flags build & validation"
Cohesion: 0.25
Nodes (4): build_args(), _flag_name(), _is_flag(), validate_settings()

### Community 41 - "Model browser scanner"
Cohesion: 0.20
Nodes (5): models_list(), _iter_files(), walk(), list_models(), _scan()

### Community 45 - "Proxy analytics plumbing"
Cohesion: 0.16
Nodes (6): get_config(), _host_without_port(), _is_loopback_host(), PanelRequestGuard, PanelTokenGate, _protected_path()

### Community 51 - "Pull request template"
Cohesion: 0.50
Nodes (3): Verified how, What, Why

## Knowledge Gaps
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Gotchas` connect `Panel security middleware & proxy core` to `Tray launcher & startup`, `FastAPI app & endpoints`, `Analytics store (SQLite)`, `llama-server process manager`, `FastAPI imports & request models`, `Git self-update & relaunch env`, `Spawn & probe helpers`, `Speculative decoding techniques`, `Frontend app shell`, `Build install & retention`, `Variant & CUDA logic`, `Release asset parsing`, `Release asset discovery`, `Backend update API & progress`, `Download, extract & verify`, `GPU probing`, `Docs & contributor conventions`, `Folder browse & path validation`, `Proxy analytics plumbing`?**
  _High betweenness centrality (0.340) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `create_app()` (e.g. with `Gotchas` and `.latest_record()`) actually correct?**
  _`create_app()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Should `Tray launcher & startup` be split into smaller, more focused modules?**
  _Cohesion score 0.06721215663354763 - nodes in this community are weakly interconnected._
- **Why does `create_app()` connect `FastAPI app & endpoints` to `Tray launcher & startup`, `Analytics store (SQLite)`, `Folder browse & path validation`, `llama-server process manager`, `FastAPI imports & request models`, `CLI flag translation`, `Flags build & validation`, `Spawn & probe helpers`, `Model browser scanner`, `Preset management`, `Proxy analytics plumbing`, `Panel security middleware & proxy core`?**
  _High betweenness centrality (0.186) - this node is a cross-community bridge._
- **Are the 79 inferred relationships involving `Gotchas` (e.g. with `_bucket_bounds()` and `_bucket_next()`) actually correct?**
  _`Gotchas` has 79 INFERRED edges - model-reasoned connections that need verification._
- **Should `FastAPI app & endpoints` be split into smaller, more focused modules?**
  _Cohesion score 0.050724637681159424 - nodes in this community are weakly interconnected._
- **Why does `LlamaServerManager` connect `llama-server process manager` to `FastAPI app & endpoints`, `Analytics store (SQLite)`, `FastAPI imports & request models`, `Spawn & probe helpers`, `Panel security middleware & proxy core`?**
  _High betweenness centrality (0.106) - this node is a cross-community bridge._