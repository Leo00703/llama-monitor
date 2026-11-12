# Graph Report - llama-monitor  (2026-11-12)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 871 nodes · 1806 edges · 51 communities (34 shown, 17 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 223 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e5d72ce7`
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
- Metrics loop & live inference stats
- Spec settings & draft validation
- Frontend app shell
- Preset management
- Build install & retention
- Variant & CUDA logic
- Release asset parsing
- Panel security middleware & proxy core
- Release asset discovery
- Release fetching
- Settings validation & spec flags
- Download, extract & verify
- Models page
- Process module & help parsing
- Service worker
- nvidia-smi & Prometheus parsing
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
- Backend update API routes
- Config persistence & mutation routes
- Frontend API client
- Ngram params schema
- NVIDIA driver detection
- Slow request logging middleware
- Config module core & host resolution
- Pull request template

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 86 edges
2. `Gotchas` - 82 edges
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
- `Gotchas` --references--> `LlamaServerManager`  [INFERRED]
  AGENTS.md → backend/process.py
- `Gotchas` --references--> `PresetRequest`  [INFERRED]
  AGENTS.md → backend/main.py
- `Gotchas` --references--> `LiveLogStats`  [INFERRED]
  AGENTS.md → backend/analytics.py
- `Gotchas` --references--> `PrintTimingTracker`  [INFERRED]
  AGENTS.md → backend/analytics.py

## Import Cycles
- None detected.

## Communities (51 total, 17 thin omitted)

### Community 0 - "Tray launcher & startup"
Cohesion: 0.05
Nodes (43): AppConfig, load_config(), set_restart_hook(), set_linger_server(), acquire_single_instance(), apply_state(), _apply_ui_now(), _bootstrap_failure() (+35 more)

### Community 1 - "FastAPI app & endpoints"
Cohesion: 0.10
Nodes (10): create_app(), analytics_models(), analytics_summary(), analytics_timeseries(), api_validate_paths(), prepare_launch(), preset_preview(), _price() (+2 more)

### Community 2 - "Analytics store (SQLite)"
Cohesion: 0.10
Nodes (8): AnalyticsStore, _avg(), _bucket_bounds(), _bucket_label(), _bucket_next(), _bucket_sequence(), _default_bucket(), _safe()

### Community 3 - "llama-server process manager"
Cohesion: 0.05
Nodes (4): Data & config, spawn_argv(), LlamaServerManager, _redact_secrets()

### Community 4 - "CLI flag translation"
Cohesion: 0.15
Nodes (31): FlagContext, _r_alias(), _r_api_key(), _r_batch(), _r_cache_reuse(), _r_cont_batching(), _r_ctk(), _r_ctv() (+23 more)

### Community 6 - "Git self-update & relaunch env"
Cohesion: 0.11
Nodes (21): parse_devices(), probe_gpu(), no_window_kwargs(), onefile_relaunch_env(), apply_update(), check(), _check_now(), consume_update_result() (+13 more)

### Community 7 - "Metrics loop & live inference stats"
Cohesion: 0.06
Nodes (9): _f(), LiveLogStats, PowerSampler, PrintTimingTracker, _tps(), _enrich_inference(), _metrics_loop(), CpuSensors (+1 more)

### Community 8 - "Spec settings & draft validation"
Cohesion: 0.12
Nodes (3): SpecSettings, _DFlash, _DSpark

### Community 9 - "Frontend app shell"
Cohesion: 0.10
Nodes (31): appendLogLine(), applyState(), autoscrollEl, badge, btnCollapse, btnRestart, btnSidebar, btnStart (+23 more)

### Community 10 - "Preset management"
Cohesion: 0.23
Nodes (3): _now(), PresetStore, Preset

### Community 11 - "Build install & retention"
Cohesion: 0.12
Nodes (11): extract_archive(), free_bytes(), local_builds(), panel_download_path(), prune(), read_manifest(), record_cuda_runtime(), resolve_storage() (+3 more)

### Community 12 - "Variant & CUDA logic"
Cohesion: 0.13
Nodes (8): cleanup_partials(), cuda_lib_patterns(), cuda_major_for_driver(), _is_panel_download(), is_valid_tag(), missing_cuda_dlls(), pick_suggested_variant(), _ver_tuple()

### Community 13 - "Release asset parsing"
Cohesion: 0.22
Nodes (6): _backend_label(), parse_build_asset(), parse_cudart_asset(), _parse_rest(), provenance(), _variant_id()

### Community 14 - "Panel security middleware & proxy core"
Cohesion: 0.06
Nodes (14): Gotchas, check_due(), is_valid_variant(), _CacheAwareStaticFiles, get_config(), _host_without_port(), _is_loopback_host(), PanelRequestGuard (+6 more)

### Community 15 - "Release asset discovery"
Cohesion: 0.16
Nodes (9): cached_variants(), companion_supported(), find_asset(), find_companion_asset(), local_arch(), local_platform(), release_assets(), suggest_variant() (+1 more)

### Community 16 - "Release fetching"
Cohesion: 0.29
Nodes (5): fetch_releases(), _fetch_releases_network(), _kick_background_refresh(), _bg(), _spawn()

### Community 17 - "Settings validation & spec flags"
Cohesion: 0.22
Nodes (4): _ngram_flags(), _r_spec(), validate_settings(), get()

### Community 20 - "Process module & help parsing"
Cohesion: 0.15
Nodes (5): parse_help(), _parse_help_output(), spec_types(), ServerState, _spawn()

### Community 22 - "nvidia-smi & Prometheus parsing"
Cohesion: 0.21
Nodes (5): _find_any(), nvidia_smi_cached(), parse_prometheus(), run_nvidia_smi(), _to_float()

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
Cohesion: 0.08
Nodes (19): BuildInfo, run_version(), browse_directory(), _count_gguf(), _is_dir(), _parent_of(), _res(), _start_dir() (+11 more)

### Community 36 - "Backend download & repair flow"
Cohesion: 0.24
Nodes (8): backend_repair(), be_download(), fail(), progress(), progress_cuda(), be_repair(), progress(), _rmtree_async()

### Community 37 - "Backend updater loop & check API"
Cohesion: 0.22
Nodes (10): LlamaBackendPending, backend_check(), backend_download(), be_loop(), be_run_check(), lifespan(), _warm_help(), _start_be_download() (+2 more)

### Community 38 - "Parallel concurrency diagnostic tool"
Cohesion: 0.31
Nodes (4): auth_headers(), main(), one_request(), open_url()

### Community 39 - "Flag argument build & extra flags"
Cohesion: 0.25
Nodes (5): build_args(), _flag_name(), _is_flag(), _r_extra(), _split_extra()

### Community 40 - "Legacy data migration & data dir"
Cohesion: 0.25
Nodes (5): default_data_dir(), _is_same_file(), _legacy_root(), migrate_legacy_data(), _same_file()

### Community 41 - "Model browser scanner"
Cohesion: 0.22
Nodes (5): models_list(), _iter_files(), walk(), list_models(), _scan()

### Community 42 - "Proxy request plumbing & analytics writes"
Cohesion: 0.25
Nodes (8): _complete_request(), llama_proxy(), _model_for_request(), _record_failure(), _submit_db_write(), _done(), _warn_key_withheld(), _model_from_args()

### Community 43 - "Backend update API routes"
Cohesion: 0.25
Nodes (8): backend_apply(), backend_gpu(), backend_suggest(), backend_versions(), be_apply(), be_current(), be_storage(), be_target_tag()

### Community 44 - "Config persistence & mutation routes"
Cohesion: 0.29
Nodes (6): save_config(), backend_set_config(), post_config(), presets_activate(), presets_create(), presets_delete()

### Community 45 - "Frontend API client"
Cohesion: 0.48
Nodes (6): API, authHeaders(), panelToken(), parseBody(), request(), unauthorizedError()

### Community 51 - "Pull request template"
Cohesion: 0.50
Nodes (3): Verified how, What, Why

## Knowledge Gaps
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Gotchas` connect `Panel security middleware & proxy core` to `Tray launcher & startup`, `FastAPI app & endpoints`, `Analytics store (SQLite)`, `llama-server process manager`, `FastAPI imports & request models`, `Git self-update & relaunch env`, `Metrics loop & live inference stats`, `Spec settings & draft validation`, `Frontend app shell`, `Build install & retention`, `Variant & CUDA logic`, `Release asset parsing`, `Release asset discovery`, `Settings validation & spec flags`, `Download, extract & verify`, `nvidia-smi & Prometheus parsing`, `Docs & contributor conventions`, `Folder browse & path validation`, `Backend updater loop & check API`, `Proxy request plumbing & analytics writes`, `Backend update API routes`, `Config persistence & mutation routes`, `Frontend API client`?**
  _High betweenness centrality (0.330) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `create_app()` (e.g. with `Gotchas` and `.latest_record()`) actually correct?**
  _`create_app()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Should `Tray launcher & startup` be split into smaller, more focused modules?**
  _Cohesion score 0.052943354313217325 - nodes in this community are weakly interconnected._
- **Why does `create_app()` connect `FastAPI app & endpoints` to `Tray launcher & startup`, `Analytics store (SQLite)`, `Folder browse & path validation`, `Backend download & repair flow`, `FastAPI imports & request models`, `Backend updater loop & check API`, `Metrics loop & live inference stats`, `Flag argument build & extra flags`, `Model browser scanner`, `Proxy request plumbing & analytics writes`, `Backend update API routes`, `Config persistence & mutation routes`, `Preset management`, `Panel security middleware & proxy core`, `llama-server process manager`, `Settings validation & spec flags`, `Process module & help parsing`, `CLI flag translation`?**
  _High betweenness centrality (0.184) - this node is a cross-community bridge._
- **Are the 81 inferred relationships involving `Gotchas` (e.g. with `_bucket_bounds()` and `_bucket_next()`) actually correct?**
  _`Gotchas` has 81 INFERRED edges - model-reasoned connections that need verification._
- **Should `FastAPI app & endpoints` be split into smaller, more focused modules?**
  _Cohesion score 0.09538461538461539 - nodes in this community are weakly interconnected._
- **Why does `LlamaServerManager` connect `llama-server process manager` to `FastAPI app & endpoints`, `FastAPI imports & request models`, `Metrics loop & live inference stats`, `Panel security middleware & proxy core`, `Process module & help parsing`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._