# Graph Report - llama-monitor  (2026-11-09)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 823 nodes · 1699 edges · 52 communities (33 shown, 19 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 218 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `09fc360f`
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
- Config models & data-dir migration
- System metrics collection
- Backend updater panel endpoints & poller
- Flags build & validation
- Analytics time bucketing & CSV export
- Model browser scanner
- print_timing block parsing
- Metrics loop & power sampling
- Path normalization & exe resolution
- Proxy analytics plumbing
- Live log tok/s parsing
- Config save & preset activation
- Launch preparation & apply endpoints
- Slow request logging middleware
- Ngram params schema
- Pull request template

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 86 edges
2. `Gotchas` - 73 edges
3. `LaunchSettings` - 56 edges
4. `LlamaServerManager` - 47 edges
5. `FlagContext` - 36 edges
6. `run_tray()` - 20 edges
7. `AnalyticsStore` - 19 edges
8. `SpecSettings` - 19 edges
9. `AppConfig` - 18 edges
10. `no_window_kwargs()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Repo layout` --references--> `_ngram_flags()`  [INFERRED]
  AGENTS.md → backend/flags.py
- `Gotchas` --references--> `LlamaServerManager`  [INFERRED]
  AGENTS.md → backend/process.py
- `Gotchas` --references--> `LiveLogStats`  [INFERRED]
  AGENTS.md → backend/analytics.py
- `Gotchas` --references--> `PresetRequest`  [INFERRED]
  AGENTS.md → backend/main.py
- `Gotchas` --references--> `SpecSettings`  [INFERRED]
  AGENTS.md → backend/schema.py

## Import Cycles
- None detected.

## Communities (52 total, 19 thin omitted)

### Community 0 - "Tray launcher & startup"
Cohesion: 0.07
Nodes (37): AppConfig, load_config(), set_restart_hook(), set_linger_server(), acquire_single_instance(), apply_state(), _bootstrap_failure(), _cleanup_stale_mei_dirs() (+29 more)

### Community 1 - "FastAPI app & endpoints"
Cohesion: 0.10
Nodes (7): create_app(), analytics_models(), analytics_summary(), analytics_timeseries(), api_validate_paths(), _price(), spec_types()

### Community 3 - "llama-server process manager"
Cohesion: 0.06
Nodes (3): Data & config, LlamaServerManager, _spawn()

### Community 4 - "CLI flag translation"
Cohesion: 0.14
Nodes (34): FlagContext, _r_alias(), _r_api_key(), _r_batch(), _r_cache_reuse(), _r_cont_batching(), _r_ctk(), _r_ctv() (+26 more)

### Community 6 - "Git self-update & relaunch env"
Cohesion: 0.11
Nodes (20): onefile_relaunch_env(), apply_update(), check(), _check_now(), consume_update_result(), current_version(), _dirty_lines(), _frozen() (+12 more)

### Community 7 - "Spawn & probe helpers"
Cohesion: 0.11
Nodes (9): no_window_kwargs(), parse_help(), _parse_help_output(), _find_any(), nvidia_smi_cached(), parse_prometheus(), run_nvidia_smi(), _to_float() (+1 more)

### Community 8 - "Speculative decoding techniques"
Cohesion: 0.12
Nodes (3): SpecSettings, _DFlash, _DSpark

### Community 9 - "Frontend app shell"
Cohesion: 0.10
Nodes (31): appendLogLine(), applyState(), autoscrollEl, badge, btnCollapse, btnRestart, btnSidebar, btnStart (+23 more)

### Community 10 - "Preset management"
Cohesion: 0.20
Nodes (3): _now(), PresetStore, Preset

### Community 11 - "Build install & retention"
Cohesion: 0.12
Nodes (9): cuda_lib_patterns(), free_bytes(), missing_cuda_dlls(), panel_download_path(), prune(), read_manifest(), record_cuda_runtime(), resolve_storage() (+1 more)

### Community 12 - "Variant & CUDA logic"
Cohesion: 0.13
Nodes (7): cleanup_partials(), cuda_major_for_driver(), _is_panel_download(), is_valid_tag(), parse_devices(), pick_suggested_variant(), _ver_tuple()

### Community 13 - "Release asset parsing"
Cohesion: 0.22
Nodes (6): _backend_label(), parse_build_asset(), parse_cudart_asset(), _parse_rest(), provenance(), _variant_id()

### Community 14 - "Panel security middleware & proxy core"
Cohesion: 0.07
Nodes (13): Gotchas, check_due(), is_valid_variant(), _CacheAwareStaticFiles, get_config(), _host_without_port(), PanelRequestGuard, PanelTokenGate (+5 more)

### Community 15 - "Release asset discovery"
Cohesion: 0.14
Nodes (10): cached_variants(), companion_supported(), find_asset(), find_companion_asset(), local_arch(), local_platform(), nvidia_driver_version(), release_assets() (+2 more)

### Community 16 - "Release fetching"
Cohesion: 0.29
Nodes (5): fetch_releases(), _fetch_releases_network(), _kick_background_refresh(), _bg(), _spawn()

### Community 17 - "Backend update API & progress"
Cohesion: 0.21
Nodes (11): BuildInfo, backend_gpu(), backend_repair(), be_download(), fail(), progress(), progress_cuda(), be_repair() (+3 more)

### Community 18 - "Download, extract & verify"
Cohesion: 0.17
Nodes (6): download_file(), extract_archive(), local_builds(), server_exe_name(), UpdateError, verify_build()

### Community 22 - "API client"
Cohesion: 0.53
Nodes (5): API, authHeaders(), panelToken(), parseBody(), request()

### Community 29 - "Settings page"
Cohesion: 0.40
Nodes (4): Browse, PATH_FIELDS, PathHints, Settings

### Community 32 - "Docs & contributor conventions"
Cohesion: 0.07
Nodes (27): Code conventions, Code graph (graphify), Commands, Context resilience (compaction), Git workflow, GitHub Issues (`gh` CLI, authenticated as `Leo00703`), Privacy — never commit user-identifying data, Project (+19 more)

### Community 33 - "Implementation Plan (requirements doc)"
Cohesion: 0.08
Nodes (25): 1. Ruolo e obiettivo, 2. Contesto hardware (ambiente reale in cui girerà), 3. Stack tecnologico richiesto, 4.10 Analytics e storico, 4.10 Analytics e storico d'uso, 4.11 Stima costo energetico, 4.1 Gestione del processo server, 4.2 Monitoraggio risorse in tempo reale (+17 more)

### Community 34 - "Folder browse & path validation"
Cohesion: 0.15
Nodes (13): run_version(), browse_directory(), _count_gguf(), _is_dir(), _parent_of(), _res(), _start_dir(), _validate_exe() (+5 more)

### Community 36 - "Config models & data-dir migration"
Cohesion: 0.13
Nodes (7): DashboardSettings, default_data_dir(), _legacy_root(), LlamaBackendSettings, migrate_legacy_data(), PanelSettings, _same_file()

### Community 38 - "Backend updater panel endpoints & poller"
Cohesion: 0.18
Nodes (13): LlamaBackendPending, backend_check(), backend_download(), backend_suggest(), backend_versions(), be_current(), be_loop(), be_run_check() (+5 more)

### Community 39 - "Flags build & validation"
Cohesion: 0.14
Nodes (7): build_args(), _flag_name(), _is_flag(), _ngram_flags(), _r_spec(), validate_settings(), get()

### Community 40 - "Analytics time bucketing & CSV export"
Cohesion: 0.26
Nodes (5): _bucket_bounds(), _bucket_label(), _bucket_next(), _bucket_sequence(), _default_bucket()

### Community 41 - "Model browser scanner"
Cohesion: 0.22
Nodes (5): models_list(), _iter_files(), walk(), list_models(), _scan()

### Community 42 - "print_timing block parsing"
Cohesion: 0.20
Nodes (3): _f(), PrintTimingTracker, _tps()

### Community 43 - "Metrics loop & power sampling"
Cohesion: 0.22
Nodes (3): PowerSampler, _enrich_inference(), _metrics_loop()

### Community 45 - "Proxy analytics plumbing"
Cohesion: 0.22
Nodes (9): _complete_request(), llama_proxy(), _model_for_request(), _record_failure(), _submit_db_write(), _done(), _warn_key_withheld(), _is_loopback_host() (+1 more)

### Community 47 - "Config save & preset activation"
Cohesion: 0.29
Nodes (6): save_config(), backend_set_config(), post_config(), presets_activate(), presets_create(), presets_delete()

### Community 48 - "Launch preparation & apply endpoints"
Cohesion: 0.33
Nodes (6): backend_apply(), be_apply(), prepare_launch(), preset_preview(), server_restart(), server_start()

### Community 51 - "Pull request template"
Cohesion: 0.50
Nodes (3): Verified how, What, Why

## Knowledge Gaps
- **19 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Gotchas` connect `Panel security middleware & proxy core` to `Tray launcher & startup`, `FastAPI app & endpoints`, `llama-server process manager`, `FastAPI imports & request models`, `Git self-update & relaunch env`, `Spawn & probe helpers`, `Speculative decoding techniques`, `Build install & retention`, `Variant & CUDA logic`, `Release asset parsing`, `Release asset discovery`, `Download, extract & verify`, `GPU probing`, `API client`, `Docs & contributor conventions`, `Folder browse & path validation`, `System metrics collection`, `Backend updater panel endpoints & poller`, `Flags build & validation`, `Analytics time bucketing & CSV export`, `Metrics loop & power sampling`, `Path normalization & exe resolution`, `Proxy analytics plumbing`, `Live log tok/s parsing`, `Config save & preset activation`, `Launch preparation & apply endpoints`?**
  _High betweenness centrality (0.244) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `create_app()` (e.g. with `Gotchas` and `.latest_record()`) actually correct?**
  _`create_app()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Should `Tray launcher & startup` be split into smaller, more focused modules?**
  _Cohesion score 0.06721215663354763 - nodes in this community are weakly interconnected._
- **Why does `create_app()` connect `FastAPI app & endpoints` to `Tray launcher & startup`, `Analytics store (SQLite)`, `llama-server process manager`, `CLI flag translation`, `FastAPI imports & request models`, `Spawn & probe helpers`, `Preset management`, `Panel security middleware & proxy core`, `Backend update API & progress`, `Folder browse & path validation`, `Config models & data-dir migration`, `System metrics collection`, `Backend updater panel endpoints & poller`, `Flags build & validation`, `Model browser scanner`, `print_timing block parsing`, `Metrics loop & power sampling`, `Proxy analytics plumbing`, `Live log tok/s parsing`, `Config save & preset activation`, `Launch preparation & apply endpoints`?**
  _High betweenness centrality (0.183) - this node is a cross-community bridge._
- **Are the 72 inferred relationships involving `Gotchas` (e.g. with `_bucket_bounds()` and `_bucket_next()`) actually correct?**
  _`Gotchas` has 72 INFERRED edges - model-reasoned connections that need verification._
- **Should `FastAPI app & endpoints` be split into smaller, more focused modules?**
  _Cohesion score 0.09881422924901186 - nodes in this community are weakly interconnected._
- **Why does `LlamaServerManager` connect `llama-server process manager` to `FastAPI app & endpoints`, `FastAPI imports & request models`, `Spawn & probe helpers`, `Metrics loop & power sampling`, `Panel security middleware & proxy core`?**
  _High betweenness centrality (0.110) - this node is a cross-community bridge._