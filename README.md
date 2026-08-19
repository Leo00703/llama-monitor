# llama-monitor

A lightweight web control panel for a local `llama-server` (llama.cpp) instance.
Run it on the same machine as the server, open it in a browser (from the same
machine or over Tailscale), and manage everything without touching the command
line:

- **Process control** — start / stop / restart `llama-server` as a child process,
  with live stdout/stderr streaming in a terminal panel.
- **Presets** — full CRUD on launch configurations, stored as *semantic*
  settings (never raw CLI strings). A translation layer converts them to real
  `llama-server` flags at launch time, and validates them against the actually
  installed version via `llama-server --help` — unknown flags are reported as
  warnings instead of blocking the start.
- **Resource monitoring** — CPU (per-core), RAM, and one card per detected GPU
  (utilization, VRAM, temperature, power draw, clocks) via `nvidia-smi`,
  plus inference metrics (prompt/generation tok/s, per-slot context usage)
  read from the server's own `/metrics` and `/slots` endpoints.
- **Generation parameters** — sampling / penalties / control fields that are
  *not* launch flags: they are injected into every proxied
  `/v1/chat/completions` and `/completion` request, so they can be changed at
  any time without restarting the server.
- **Model browser** — recursive scan of `models_root` for `.gguf` files with
  size/sort, plus automatic mmproj (vision) projectors detection per model.

## Screenshots

Desktop view:

![llama-monitor — desktop view](docs/llama-monitor-desktop.png)

Mobile view:

![llama-monitor — mobile view](docs/llama-monitor-mobile.jpg)

## Requirements

- Python 3.10+ (tested on 3.11/3.14)
- Windows or Linux
- A `llama-server` binary (llama.cpp) on the same machine — **only needed to
  launch the server**; the panel, monitoring, model browser, and presets all
  work without it (Start/Restart just fail until the exe path is set)
- NVIDIA GPU driver providing `nvidia-smi` (optional — GPU cards are hidden
  when no GPU is detected; works on CPU-only machines too)

## Install

```bash
git clone https://github.com/Leo00703/llama-monitor
cd llama-monitor
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

All persistent data (config, presets, analytics history) lives in a stable
per-user directory **outside the repository**, so `git pull`, fresh clones,
`git clean`, or sync tools can never wipe it:

- Windows: `%APPDATA%\llama-monitor\`
- Linux/macOS: `~/.config/llama-monitor/` (or `$XDG_CONFIG_HOME/llama-monitor`)
- Override: set the `LLAMA_MONITOR_DATA` environment variable

On first start the config is seeded from `config.example.json` (or migrated
from a legacy in-repo `config.json` / `data/` if present). Edit it with the
in-app **Settings** page (which shows the data directory in use):

| Key | Meaning |
| --- | --- |
| `llama_server_exe` | Path to the `llama-server` executable (or a bare name found in `PATH`) |
| `models_root` | Root folder scanned for `.gguf` models; preset model paths are relative to it |
| `default_server_port` | Port assumed for external/ready checks when nothing else is known |
| `panel.host` / `panel.port` | Bind address/port of the panel itself (default `0.0.0.0:8000`, so it is reachable over Tailscale) |
| `active_preset_id` | Preset currently selected for launches |

## Run

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Then open `http://<server-ip>:8000` in a browser. Point your OpenAI-compatible
clients at `http://<server-ip>:8000/proxy/v1/...` to have generation parameters
applied to every request through the panel.

> Note: the panel only manages `llama-server` processes it started itself.
> If a server is already running on the configured port, the panel marks it
> as **external** and can still stop it.

## Tray launcher (Windows .exe)

For Windows there is a single-file `.exe` that runs the whole panel in the
system tray — no console, no browser tab needed for the panel itself. The tray
icon mirrors the server state (colored status dot + tooltip) and its menu has
**Open panel**, **Start / Stop server**, and **Quit**. The panel is embedded in
the same process (uvicorn in a daemon thread) on the configured
`panel.host:panel.port`, so OpenAI-compatible proxying works exactly as above.

- **Download** — the latest build is uploaded as an artifact by the
  `Build Windows tray exe` GitHub Actions workflow on every push to `main`
  (or run the workflow manually).
- **Build locally** — `build_exe.bat` (creates/updates `.venv`, installs deps,
  runs a headless smoke test, then PyInstaller) produces
  `dist\llama-monitor.exe`.
- **Run from source** — `python tray.py` (Windows only; `--smoke` runs the
  headless self-test used by CI).

A single-instance mutex prevents duplicate panels; a log is written to
`launcher.log` in the data directory.

## Project layout

```
backend/
  main.py        FastAPI app: REST API, WebSockets, static frontend
  config.py      config loading/saving + user-data-dir resolution & legacy migration
  schema.py      Pydantic models for launch settings, specs, and API payloads
  process.py     llama-server child-process manager (state machine, log capture)
  flags.py       semantic settings -> CLI flags translation + --help validation
  presets.py     preset CRUD (JSON files under <data-dir>/presets)
  metrics.py     CPU/RAM (psutil), GPU (nvidia-smi), inference metrics
  models.py      recursive .gguf browser + mmproj detection
  proxy.py       /v1/chat/completions & /completion proxy with settings injection
frontend/
  index.html     single-page app (vanilla HTML/CSS/JS, no build step)
  css/style.css  dark frosted-glass theme
   js/            app shell (app.js), api/ui/metrics helpers, pages/ (dashboard,
                  generation, presets, models, settings)
tray.py          Windows system-tray launcher (embeds the panel, --smoke self-test)
build_exe.bat    local PyInstaller build of dist\llama-monitor.exe
requirements-tray.txt   extra deps for the tray launcher (pystray, Pillow, pyinstaller)
assets/tray/     tray mark (PNG) + exe icon (ICO)
.github/workflows/build-exe.yml   CI: smoke test + PyInstaller + artifact upload
```

Persistent data lives outside the repo (see Configure): config.json,
presets/, analytics.db under `%APPDATA%\llama-monitor` (Windows) or
`~/.config/llama-monitor` (Linux/macOS).

## Development phases

The panel is built in incremental phases (see `Implementation Plan.md`):

1. Process start/stop/restart + live log streaming — done
2. Preset system (CRUD, JSON storage, flag translation layer) — done
3. Resource monitoring (CPU/RAM/GPU, inference metrics) with history charts — done
4. Model browser, mmproj, speculative decoding, generation parameters + proxy — done
5. Analytics: usage history (SQLite), energy cost, historical charts — done
6. Header (status/version/host), collapsible sidebar, design polish — done
