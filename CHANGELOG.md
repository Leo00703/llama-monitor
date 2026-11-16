# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-16

First public release and the first version tag. It marks everything the panel
has shipped so far, built incrementally through six phases (see
`Implementation Plan.md`).

### Added — process control
- Start / stop / restart a `llama-server` child process from the browser with
  live stdout/stderr streaming.
- Launch-command preview with a copy button (cmd / PowerShell / bash selector)
  that produces a paste-ready single command.
- Adoption of an already-running `llama-server` as an **external** server;
  processes that are not `llama-server` are never stopped or killed.

### Added — presets & launch translation
- Full CRUD on launch configurations stored as *semantic* settings (never raw
  CLI strings), translated to real `llama-server` flags and validated against
  the installed build via `llama-server --help`.
- Live-active preset selection persisted for the tray and the proxy fallback.
- Concurrency per preset: parallel slots (`-np`, auto by default), continuous
  batching, unified KV (auto / on / off).

### Added — speculative decoding
- Draft-model techniques: MTP, DFlash (incl. auto-detected DFlash2), DSpark,
  draft-simple, EAGLE-3 — each combinable with any of the five ngram fallbacks
  (`ngram-simple`, `ngram-map-k`, `ngram-map-k4v`, `ngram-mod`, `ngram-cache`),
  or ngrams alone with no drafter.
- Comma-list `--spec-type` emission, per-type lookup parameters, and grey-out /
  blocking of types the installed build does not document.

### Added — monitoring & analytics
- CPU (per-core), RAM and per-GPU cards via `psutil` / `nvidia-smi`; an explicit
  "No GPU detected" note on machines with no NVIDIA GPU (incl. Apple Silicon).
- Live inference metrics (prompt/generation tok/s, per-slot context, draft
  acceptance) from the server's own log lines, with `/slots` and `/metrics` as
  fallbacks.
- Per-request history (tokens, latency, energy estimate) in SQLite: summary
  cards, charts, model breakdown, request table, CSV export, range picker.

### Added — proxy & generation parameters
- OpenAI-compatible `/proxy/v1/chat/completions` and `/completion` proxy that
  injects per-preset generation parameters into every request.
- Streaming and non-streaming responses mirror the upstream status code and
  headers; failed generations are counted in analytics.

### Added — models & paths
- Recursive `.gguf` model browser with automatic mmproj (vision) detection.
- In-app path pickers (`/api/browse`) and live path-field validation for the
  Settings paths, with canonicalized path storage.

### Added — panel access control
- Binds to `127.0.0.1` by default; opt-in `0.0.0.0` with an optional panel
  token; Host/Origin/`Sec-Fetch-Site` request guard; caller-scoped API-key
  injection through the proxy; optional TLS.

### Added — updates & distribution
- Panel self-update (`git merge --ff-only`) with a running server kept across
  the update, and a llama.cpp build updater (stable/nightly, variant discovery,
  CUDA runtime companion fetch, verify-before-run, retention/rollback).
- Windows single-file tray launcher (`llama-monitor.exe`, CI-built and tracked
  at the repo root) plus a source/`uvicorn` path for Windows / Linux / macOS.
- Installable PWA (network-first shell cache; live data never cached).

### Security
- Hash-locked, `--require-hashes` CI dependency install; SHA-pinned workflow
  actions; download integrity (declared size + published asset sha256 digest +
  optional user pin) and `--version` verification before a downloaded build runs.
- See [`SECURITY.md`](SECURITY.md) for the trust model and reporting policy.

[Unreleased]: https://github.com/Leo00703/llama-monitor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Leo00703/llama-monitor/releases/tag/v0.1.0
