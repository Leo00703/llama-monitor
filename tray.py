"""llama-monitor system-tray launcher (Windows).

Embeds the FastAPI panel (uvicorn) in a daemon thread and shows a system-tray
icon (pystray) that mirrors server state and offers start / stop / open-panel.
Build into a single .exe with PyInstaller (see build_exe.bat / CI).
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import httpx
import pystray
import uvicorn
from PIL import Image, ImageDraw

from backend.config import (
    DATA_DIR, AppConfig, load_config, no_window_kwargs, onefile_relaunch_env
)
from backend.main import create_app, set_restart_hook
from backend.process import set_linger_server

# Named for the historical exe (llama-monitor-tray.exe); the exe was renamed
# to llama-monitor.exe but the name is kept so old + new builds still count
# as one instance (a renamed mutex would let both run and fight over the port).
MUTEX_NAME = "Local\\llama-monitor-tray"
POLL_INTERVAL = 2.0
HEALTH_TIMEOUT = 30.0
TRAY_SIZE = 64
ERROR_ALREADY_EXISTS = 183

STATE_META = {
    "running": ("Running", (34, 197, 94)),
    "external": ("External server", (34, 197, 94)),
    "starting": ("Starting", (234, 179, 8)),
    "restarting": ("Restarting", (234, 179, 8)),
    "error": ("Error", (239, 68, 68)),
    "stopped": ("Stopped", (156, 163, 175)),
}

log = logging.getLogger("llama-monitor.tray")

_state = {"state": "stopped", "label": "Starting…", "error": ""}
_preset_id = ""
_mark: Optional[Image.Image] = None
_dot_cache: dict = {}
_icon: Optional[pystray.Icon] = None
_mutex = None
_stop = threading.Event()
_config_ref: Optional[AppConfig] = None
_panel_browser_url = ""


def resource_dir() -> Path:
    """Directory that holds bundled resources (frontend, config.example.json, assets)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def local_host(config: AppConfig) -> str:
    host = (config.panel.host or "127.0.0.1").strip()
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return host


def panel_url(config: AppConfig) -> str:
    # https when TLS is configured: PWA installs need a secure context,
    # and https on localhost / tailscale works without extra setup
    scheme = "https" if config.panel.tls_cert.strip() else "http"
    return f"{scheme}://{local_host(config)}:{config.panel.port}"


def _panel_verify(url: str) -> bool:
    # https is never verified: the cert on a private network is self-signed
    # or a tailscale cert the host may not trust, and the traffic never
    # leaves the user's own networks
    return not url.startswith("https")


def _panel_get(url: str, path: str, timeout: float):
    return httpx.get(f"{url}{path}", timeout=timeout, verify=_panel_verify(url))


def _panel_post(url: str, path: str, timeout: float, **kwargs):
    return httpx.post(f"{url}{path}", timeout=timeout, verify=_panel_verify(url),
                      **kwargs)


def load_mark() -> Image.Image:
    global _mark
    if _mark is None:
        path = resource_dir() / "assets" / "tray" / "mark-white.png"
        _mark = Image.open(path).convert("RGBA")
    return _mark


def dot_image(color) -> Image.Image:
    """The mark with a small status dot in the corner, cached per colour."""
    key = tuple(color)
    if key in _dot_cache:
        return _dot_cache[key]
    img = load_mark().resize((TRAY_SIZE, TRAY_SIZE), Image.Resampling.LANCZOS).copy()
    draw = ImageDraw.Draw(img)
    r = TRAY_SIZE // 8
    cx = cy = TRAY_SIZE - r - 1
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 255))
    r2 = max(2, r - 2)
    draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=(*color, 255))
    _dot_cache[key] = img
    return img


def tray_title(state: str, label: str, error: str = "") -> str:
    title = f"llama-monitor — {label}"
    if state == "error" and error:
        e = error.strip()
        if len(e) > 200:
            e = e[:197] + "…"
        title += f": {e}"
    return title


def apply_state(icon: pystray.Icon, state: str, error: str = "") -> None:
    label, color = STATE_META.get(state, STATE_META["stopped"])
    _state.update({"state": state, "label": label, "error": error or ""})
    icon.icon = dot_image(color)
    icon.title = tray_title(state, label, error or "")
    icon.update_menu()


def start_panel(config: AppConfig) -> tuple[threading.Thread, uvicorn.Server]:
    app = create_app()
    ssl_kwargs = {}
    if config.panel.tls_cert.strip():
        if not config.panel.tls_key.strip():
            log.warning("panel.tls_cert set but panel.tls_key is empty — "
                        "starting without TLS")
        else:
            ssl_kwargs = {
                "ssl_certfile": config.panel.tls_cert,
                "ssl_keyfile": config.panel.tls_key,
            }
    cfg = uvicorn.Config(
        app,
        host=config.panel.host or "0.0.0.0",
        port=config.panel.port,
        log_level="warning",
        lifespan="on",
        **ssl_kwargs,
    )
    server = uvicorn.Server(cfg)

    def _run() -> None:
        try:
            server.run()
        except BaseException:
            log.exception("uvicorn server thread crashed")
            raise

    thread = threading.Thread(target=_run, name="uvicorn", daemon=True)
    thread.start()
    return thread, server


def wait_health(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not _stop.is_set():
        try:
            if _panel_get(url, "/api/health", 2.0).json().get("ok"):
                return True
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(0.4)
    return False


def poll_loop(config: AppConfig, icon: pystray.Icon) -> None:
    global _preset_id
    base = panel_url(config)
    last = object()
    while not _stop.is_set():
        try:
            state = _panel_get(base, "/api/state", 3.0).json()
            cfg = _panel_get(base, "/api/config", 3.0).json()
            preset_id = cfg.get("active_preset_id") or ""
            # the error text is part of the key: a changed error while the
            # state stays "error" must refresh the tooltip
            key = (state.get("state"), preset_id, state.get("error") or "")
            if key != last:
                _preset_id = preset_id
                apply_state(icon, state.get("state") or "stopped", state.get("error") or "")
                last = key
        except (httpx.HTTPError, ValueError):
            pass
        _stop.wait(POLL_INTERVAL)


def _menu_items() -> list:
    state = _state["state"]
    items = [
        pystray.MenuItem(f"llama-monitor — {_state['label']}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open panel", open_panel, default=True),
    ]
    if state in ("stopped", "error"):
        items.append(
            pystray.MenuItem(
                "Start server",
                toggle_server,
                enabled=bool(_preset_id),
            )
        )
    else:
        items.append(pystray.MenuItem("Stop server", toggle_server))
    items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem("Quit", quit_app))
    return items


def open_panel() -> None:
    def _open() -> None:
        try:
            webbrowser.open(_panel_browser_url)
        except Exception:
            log.exception("failed to open panel in browser")

    threading.Thread(target=_open, daemon=True).start()


def toggle_server() -> None:
    def _toggle() -> None:
        base = panel_url(_config_ref)
        try:
            if _state["state"] in ("stopped", "error"):
                if not _preset_id:
                    _notify("No preset selected", "Select an active preset in the panel first.")
                    return
                _panel_post(
                    base, "/api/server/start",
                    json={"args": [], "preset_id": _preset_id},
                    timeout=10.0,
                )
            else:
                _panel_post(base, "/api/server/stop", timeout=10.0)
        except httpx.HTTPError as exc:
            log.exception("server control failed")
            _notify("Action failed", str(exc))

    threading.Thread(target=_toggle, daemon=True).start()


def _notify(title: str, message: str) -> None:
    if _icon is not None:
        try:
            _icon.notify(message, title)
        except Exception:
            log.exception("tray notification failed")


def quit_app() -> None:
    _stop.set()
    if _icon is not None:
        _icon.stop()


def acquire_single_instance() -> bool:
    global _mutex
    kernel32 = ctypes.windll.kernel32
    _mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def _message_box(title: str, text: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)


def _restart_app(deferred: bool = False) -> None:
    """Quit cleanly after an update (the relaunch handoff).

    deferred=False: spawn the relaunched launcher (direct update — it
    retries the single-instance mutex and waits for this panel to release
    its port). deferred=True: the update-bootstrap ps1 performs the merge
    AFTER this process exits and relaunches the app itself — spawn nothing,
    just shut down. In both cases the llama-server child is left running
    (set_linger_server): the relaunched panel adopts it as an external
    server, so an in-flight inference survives the update and this process
    exits without the stop-timeout waits.
    """
    set_linger_server()
    if deferred:
        log.info("update: deferred bootstrap relaunch — exiting without spawning")
        _stop.set()
        if _icon is not None:
            _icon.stop()
        return
    log.info("update: relaunching the launcher")
    try:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--restarting"]
        else:
            cmd = [sys.executable, str(Path(__file__).resolve()), "--restarting"]
        kwargs = dict(no_window_kwargs())
        if os.name == "nt":
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.DETACHED_PROCESS
        # The frozen app's env carries onefile _PYI_* role vars — a fresh
        # copy of the exe must start as a top-level launcher (see
        # onefile_relaunch_env()).
        kwargs["env"] = onefile_relaunch_env()
        subprocess.Popen(cmd, **kwargs)
    except Exception:
        log.exception("update: failed to spawn the relaunch process — staying up")
        return
    _stop.set()
    if _icon is not None:
        _icon.stop()


def _cleanup_stale_mei_dirs() -> None:
    """Remove leftover PyInstaller onefile temp dirs (_MEI*) older than a day.

    A stuck bootloader parent that the update helper had to force-kill (the
    "Failed to remove temporary directory" dialog) — or a crash — leaves its
    _MEI* extraction dir behind (~25MB each). A live instance's dir is always
    fresh, so anything older than 24h is safe to remove. Best-effort.
    """
    if os.name != "nt":
        return
    try:
        temp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "")
        if not temp.is_dir():
            return
        cutoff = time.time() - 86400
        for d in temp.glob("_MEI*"):
            try:
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass
    except Exception:
        log.exception("stale _MEI cleanup failed")


def _install_stdout_stderr() -> None:
    # In a --noconsole frozen build sys.stdout/sys.stderr are None. uvicorn's
    # default logging config builds StreamHandlers off sys.stderr, so the first
    # log emit would raise in the (daemon) uvicorn thread and kill the panel.
    # Point both at the null device so those handlers have a valid sink.
    if getattr(sys, "frozen", False) and sys.stdout is None and sys.stderr is None:
        sink = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sink
        sys.stderr = sink


def setup_logging() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(DATA_DIR / "launcher.log", encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def shutdown_panel(thread: threading.Thread, server: uvicorn.Server) -> None:
    server.should_exit = True
    thread.join(timeout=20)
    if thread.is_alive():
        server.force_exit = True
        thread.join(timeout=10)


def run_smoke() -> int:
    """Headless self-test used by CI: boot the panel, hit /api/health, exit."""
    setup_logging()
    try:
        config = load_config()
    except RuntimeError as exc:
        print(f"smoke FAIL: {exc}")
        return 1
    url = panel_url(config)
    log.info("smoke: starting panel on %s", url)
    panel_thread, server = start_panel(config)
    if wait_health(url, HEALTH_TIMEOUT):
        print(f"smoke OK: panel healthy at {url}")
    else:
        print(f"smoke FAIL: panel not healthy at {url}")
        shutdown_panel(panel_thread, server)
        return 1
    shutdown_panel(panel_thread, server)
    print("smoke OK: panel shut down cleanly")
    return 0


def run_tray(restarting: bool = False) -> int:
    global _icon, _config_ref, _panel_browser_url, _preset_id
    _install_stdout_stderr()
    _cleanup_stale_mei_dirs()
    setup_logging()
    if restarting:
        log.info("restart handoff: waiting for the previous instance to exit")
        deadline = time.time() + 60.0
        acquired = False
        while time.time() < deadline:
            if acquire_single_instance():
                acquired = True
                break
            time.sleep(0.5)
        if not acquired:
            _message_box("llama-monitor", "The previous instance did not release its lock in time.")
            return 1
    elif not acquire_single_instance():
        _message_box("llama-monitor", "llama-monitor is already running (see system tray).")
        return 0

    try:
        config = load_config()
    except RuntimeError as exc:
        _message_box("llama-monitor", f"Could not read configuration:\n{exc}")
        return 1

    _config_ref = config
    _panel_browser_url = panel_url(config)
    url = panel_url(config)

    set_restart_hook(_restart_app)

    if restarting:
        # The old process releases its port before its mutex (the panel
        # shuts down before the process exits); wait for the port to be
        # free before binding our own.
        deadline = time.time() + 60.0
        while time.time() < deadline:
            try:
                _panel_get(url, "/api/health", 1.0)
            except httpx.HTTPError:
                break
            time.sleep(0.5)

    log.info("starting panel on %s", url)
    thread, server = start_panel(config)
    if not wait_health(url, HEALTH_TIMEOUT):
        shutdown_panel(thread, server)
        _message_box(
            "llama-monitor",
            f"The panel could not start on {url}.\n"
            "The port may be in use by another instance.",
        )
        return 1

    try:
        initial = _panel_get(url, "/api/state", 3.0).json()
    except (httpx.HTTPError, ValueError):
        initial = {"state": "stopped"}
    initial_preset = ""
    try:
        initial_preset = _panel_get(url, "/api/config", 3.0).json().get(
            "active_preset_id"
        ) or ""
    except (httpx.HTTPError, ValueError):
        pass
    _preset_id = initial_preset

    label, color = STATE_META.get(initial.get("state"), STATE_META["stopped"])
    _state.update(
        {"state": initial.get("state", "stopped"), "label": label,
         "error": initial.get("error") or ""}
    )

    icon = pystray.Icon(
        "llama-monitor",
        dot_image(color),
        tray_title(initial.get("state", "stopped"), label, initial.get("error") or ""),
        pystray.Menu(_menu_items),
    )
    _icon = icon

    poller = threading.Thread(
        target=poll_loop, args=(config, icon), name="tray-poller", daemon=True
    )
    poller.start()

    icon.run()

    log.info("tray loop exited, shutting down panel")
    _stop.set()
    shutdown_panel(thread, server)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="llama-monitor tray launcher")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="headless self-test: boot the panel, check health, exit",
    )
    parser.add_argument(
        "--restarting",
        action="store_true",
        help="internal: relaunched after an update — wait for the previous instance",
    )
    args = parser.parse_args()

    if args.smoke:
        return run_smoke()

    if os.name != "nt":
        print("The tray launcher is only available on Windows.")
        return 2

    return run_tray(restarting=args.restarting)


if __name__ == "__main__":
    sys.exit(main())
