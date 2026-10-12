# Graph Report - llama-monitor  (2026-10-12)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 682 nodes · 1400 edges · 32 communities (16 shown, 16 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 136 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `25ad3a05`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Tray launcher & startup
- FastAPI app & endpoints
- Analytics & log stats
- llama-server process manager
- CLI flag translation
- Static serving & model browser
- Config models & git self-update
- System metrics collection
- Speculative decoding techniques
- Frontend app shell
- Preset management
- Build install & retention
- Variant & CUDA logic
- Release asset parsing
- Inference proxy
- Release asset discovery
- Release fetching
- Build provenance
- Download & errors
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

## God Nodes (most connected - your core abstractions)
1. `create_app()` - 78 edges
2. `LaunchSettings` - 56 edges
3. `LlamaServerManager` - 42 edges
4. `FlagContext` - 36 edges
5. `run_tray()` - 19 edges
6. `SpecSettings` - 18 edges
7. `AppConfig` - 17 edges
8. `AnalyticsStore` - 17 edges
9. `no_window_kwargs()` - 17 edges
10. `Technique` - 15 edges

## Surprising Connections (you probably didn't know these)
- `_load_stack()` --uses--> `AppConfig`  [INFERRED]
  tray.py → backend/config.py
- `_restart_app()` --calls--> `no_window_kwargs()`  [EXTRACTED]
  tray.py → backend/config.py
- `_restart_app()` --calls--> `onefile_relaunch_env()`  [EXTRACTED]
  tray.py → backend/config.py
- `start_panel()` --calls--> `create_app()`  [EXTRACTED]
  tray.py → backend/main.py
- `create_app()` --uses--> `AppConfig`  [INFERRED]
  backend/main.py → backend/config.py

## Import Cycles
- None detected.

## Communities (32 total, 16 thin omitted)

### Community 0 - "Tray launcher & startup"
Cohesion: 0.06
Nodes (37): AppConfig, load_config(), resolve_exe_path(), set_restart_hook(), set_linger_server(), acquire_single_instance(), apply_state(), _bootstrap_failure() (+29 more)

### Community 1 - "FastAPI app & endpoints"
Cohesion: 0.05
Nodes (43): LlamaBackendPending, save_config(), create_app(), analytics_models(), analytics_summary(), analytics_timeseries(), backend_apply(), backend_check() (+35 more)

### Community 2 - "Analytics & log stats"
Cohesion: 0.05
Nodes (14): AnalyticsStore, _avg(), _bucket_bounds(), _bucket_label(), _bucket_next(), _bucket_sequence(), _default_bucket(), _f() (+6 more)

### Community 4 - "CLI flag translation"
Cohesion: 0.09
Nodes (41): build_args(), _flag_name(), FlagContext, _is_flag(), _ngram_flags(), _r_alias(), _r_api_key(), _r_batch() (+33 more)

### Community 5 - "Static serving & model browser"
Cohesion: 0.05
Nodes (13): _CacheAwareStaticFiles, models_list(), _model_from_args(), PresetRequest, SlowRequestLogger, StartRequest, _update_loop(), _iter_files() (+5 more)

### Community 6 - "Config models & git self-update"
Cohesion: 0.08
Nodes (26): DashboardSettings, default_data_dir(), _legacy_root(), LlamaBackendSettings, migrate_legacy_data(), no_window_kwargs(), onefile_relaunch_env(), PanelSettings (+18 more)

### Community 7 - "System metrics collection"
Cohesion: 0.07
Nodes (10): parse_help(), _parse_help_output(), spec_types(), CpuSensors, _find_any(), MetricsCollector, parse_prometheus(), run_nvidia_smi() (+2 more)

### Community 8 - "Speculative decoding techniques"
Cohesion: 0.09
Nodes (4): SpecSettings, Technique, _DFlash, _DSpark

### Community 9 - "Frontend app shell"
Cohesion: 0.10
Nodes (30): appendLogLine(), applyState(), autoscrollEl, badge, btnCollapse, btnRestart, btnSidebar, btnStart (+22 more)

### Community 10 - "Preset management"
Cohesion: 0.14
Nodes (5): _now(), PresetStore, NgramLookupSettings, NgramModSettings, Preset

### Community 11 - "Build install & retention"
Cohesion: 0.12
Nodes (11): cleanup_partials(), extract_archive(), free_bytes(), local_builds(), prune(), read_manifest(), record_cuda_runtime(), resolve_storage() (+3 more)

### Community 12 - "Variant & CUDA logic"
Cohesion: 0.14
Nodes (7): check_due(), cuda_lib_patterns(), cuda_major_for_driver(), is_valid_variant(), missing_cuda_dlls(), pick_suggested_variant(), _ver_tuple()

### Community 13 - "Release asset parsing"
Cohesion: 0.15
Nodes (9): _backend_label(), cached_variants(), nvidia_driver_version(), parse_build_asset(), parse_cudart_asset(), _parse_rest(), suggest_variant(), _variant_id() (+1 more)

### Community 15 - "Release asset discovery"
Cohesion: 0.22
Nodes (6): companion_supported(), find_asset(), find_companion_asset(), local_arch(), local_platform(), release_assets()

### Community 16 - "Release fetching"
Cohesion: 0.33
Nodes (4): fetch_releases(), _fetch_releases_network(), _kick_background_refresh(), _bg()

### Community 17 - "Build provenance"
Cohesion: 0.33
Nodes (3): BuildInfo, provenance(), run_version()

## Knowledge Gaps
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `create_app()` connect `FastAPI app & endpoints` to `Tray launcher & startup`, `Analytics & log stats`, `llama-server process manager`, `CLI flag translation`, `Static serving & model browser`, `Config models & git self-update`, `System metrics collection`, `Preset management`, `Inference proxy`?**
  _High betweenness centrality (0.210) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `create_app()` (e.g. with `.latest_record()` and `AppConfig`) actually correct?**
  _`create_app()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Should `Tray launcher & startup` be split into smaller, more focused modules?**
  _Cohesion score 0.05853174603174603 - nodes in this community are weakly interconnected._
- **Why does `LlamaServerManager` connect `llama-server process manager` to `FastAPI app & endpoints`, `Analytics & log stats`, `Static serving & model browser`, `System metrics collection`?**
  _High betweenness centrality (0.120) - this node is a cross-community bridge._
- **Are the 40 inferred relationships involving `LaunchSettings` (e.g. with `build_args()` and `_r_alias()`) actually correct?**
  _`LaunchSettings` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Should `FastAPI app & endpoints` be split into smaller, more focused modules?**
  _Cohesion score 0.05357142857142857 - nodes in this community are weakly interconnected._
- **Why does `LaunchSettings` connect `CLI flag translation` to `Speculative decoding techniques`, `FastAPI app & endpoints`, `Preset management`, `Static serving & model browser`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._