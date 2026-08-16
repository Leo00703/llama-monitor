"""llama-server child-process management: start/stop/restart, state machine,
live stdout/stderr capture broadcast over WebSockets."""

from __future__ import annotations

import asyncio
import collections
import contextlib
import logging
import os
import signal
import socket
import subprocess
from enum import Enum
from typing import Any, Callable, Optional

import psutil

log = logging.getLogger("llama-monitor.process")

LOG_BUFFER_SIZE = 4000
STOP_TIMEOUT = 10.0
KILL_TIMEOUT = 5.0


class ServerState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RESTARTING = "restarting"
    ERROR = "error"
    EXTERNAL = "external"


class LlamaServerManager:
    """Owns the llama-server child process and streams its output.

    State transitions:
      stopped -> starting -> running -> stopped
                                     -> error (unexpected exit / start failure)
      stopped -> external (port occupied by a process not started by the panel)
    """

    def __init__(self, get_config: Callable[[], Any]) -> None:
        self._get_config = get_config
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._state = ServerState.STOPPED
        self._error = ""
        self._version = ""
        self._log: collections.deque[str] = collections.deque(maxlen=LOG_BUFFER_SIZE)
        self._listeners: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._launch_args: list[str] = []
        self._stop_requested = False

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def on_startup(self) -> None:
        self._version = await self._detect_version()
        self._detect_external()
        self._publish_state()

    async def shutdown(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            await self.stop()

    # ------------------------------------------------------------------
    # control
    # ------------------------------------------------------------------

    async def start(self, args: list[str]) -> dict:
        async with self._lock:
            if self._state in (ServerState.STARTING, ServerState.RUNNING,
                               ServerState.RESTARTING, ServerState.EXTERNAL):
                return {"ok": False, "error": f"server is {self._state.value}"}

            exe = self._get_config().resolved_exe()
            if not exe:
                msg = "llama-server executable not configured (see Settings)"
                self._set_error_state(msg)
                return {"ok": False, "error": msg}

            port = self._port_from_args(args) or self._get_config().default_server_port
            if self._pid_on_port(port) is not None:
                msg = f"port {port} is already in use"
                self._set_error_state(msg)
                return {"ok": False, "error": msg}

            self._stop_requested = False
            self._error = ""
            self._state = ServerState.STARTING
            self._publish_state()
            cmd = " ".join([exe, *args])
            self._publish_log(f"[panel] starting: {cmd}")
            log.info("starting: %s", cmd)
            try:
                self._proc = await asyncio.create_subprocess_exec(
                    exe, *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    **self._spawn_kwargs(),
                )
            except OSError as exc:
                msg = f"failed to start process: {exc}"
                self._publish_log(f"[panel] {msg}")
                self._set_error_state(msg)
                return {"ok": False, "error": msg}

            self._launch_args = args
            pid = self._proc.pid
            asyncio.create_task(self._read_output(self._proc))
            asyncio.create_task(self._run_monitor(self._proc, port))
            return {"ok": True, "state": self._state.value, "pid": pid}

    async def stop(self) -> dict:
        async with self._lock:
            proc = self._proc
            if proc is not None and proc.returncode is None:
                self._stop_requested = True
                self._publish_log("[panel] stopping server...")
                self._terminate(proc)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=STOP_TIMEOUT)
                except asyncio.TimeoutError:
                    self._publish_log("[panel] graceful stop timed out, killing process")
                    self._kill(proc)
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(proc.wait(), timeout=KILL_TIMEOUT)
                self._proc = None
                self._state = ServerState.STOPPED
                self._error = ""
                self._publish_log("[panel] server stopped")
                self._publish_state()
                return {"ok": True, "state": self._state.value}

            # No child process: maybe an external server occupies the port.
            pid = self._pid_on_port(self._get_config().default_server_port)
            if pid is not None:
                self._publish_log(f"[panel] stopping external server (pid {pid})")
                self._terminate_pid(pid)
                try:
                    psutil.Process(pid)
                    for _ in range(int(STOP_TIMEOUT * 10)):
                        if not psutil.pid_exists(pid):
                            break
                        await asyncio.sleep(0.1)
                    else:
                        with contextlib.suppress(psutil.Error):
                            psutil.Process(pid).kill()
                except psutil.Error:
                    pass
                self._state = ServerState.STOPPED
                self._error = ""
                self._publish_log("[panel] external server stopped")
                self._publish_state()
                return {"ok": True, "state": self._state.value}

            self._state = ServerState.STOPPED
            self._error = ""
            self._publish_state()
            return {"ok": True, "state": self._state.value}

    async def restart(self, args: Optional[list[str]] = None) -> dict:
        """Stop (if running) and start again. Falls back to last launch args."""
        use_args = args if args is not None else self._launch_args
        if not use_args:
            return {"ok": False, "error": "no launch arguments to restart with"}
        await self.stop()
        return await self.start(use_args)

    # ------------------------------------------------------------------
    # introspection
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        return {
            "state": self._state.value,
            "pid": self._proc.pid if self._proc is not None and self._proc.returncode is None else None,
            "version": self._version,
            "error": self._error,
        }

    def log_history(self) -> list[str]:
        return list(self._log)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self._listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._listeners.discard(queue)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _publish_log(self, line: str) -> None:
        self._log.append(line)
        self._broadcast({"type": "log", "line": line})

    def _publish_state(self) -> None:
        self._broadcast({"type": "state", **self.snapshot()})

    def _broadcast(self, event: dict) -> None:
        for queue in list(self._listeners):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    def _set_error_state(self, message: str) -> None:
        self._state = ServerState.ERROR
        self._error = message
        self._publish_log(f"[panel] error: {message}")
        self._publish_state()

    def _detect_external(self) -> None:
        """If a llama-server (or anything) already listens on the port, mark it."""
        port = self._get_config().default_server_port
        pid = self._pid_on_port(port)
        if pid is not None and (self._proc is None or self._proc.returncode is not None):
            self._state = ServerState.EXTERNAL
            self._error = f"port {port} is occupied by pid {pid} (not started by this panel)"
            self._publish_log(f"[panel] detected external server on port {port} (pid {pid})")

    async def _read_output(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip("\n")
            if text:
                self._publish_log(text)

    async def _run_monitor(self, proc: asyncio.subprocess.Process, port: int) -> None:
        """Wait until the server accepts connections, then watch for exit."""
        ready = False
        while proc.returncode is None and not ready and not self._stop_requested:
            await asyncio.sleep(0.4)
            if await self._port_open(port):
                ready = True
        if ready and proc.returncode is None:
            self._state = ServerState.RUNNING
            self._error = ""
            self._publish_log("[panel] server is up and accepting connections")
            self._publish_state()
        code = await proc.wait()
        if self._stop_requested or code in (0, None):
            if self._state not in (ServerState.STOPPED,):
                self._state = ServerState.STOPPED
                self._error = ""
                self._publish_state()
        else:
            if self._state != ServerState.ERROR:
                self._error = f"process exited with code {code}"
                self._publish_log(f"[panel] server exited unexpectedly (code {code})")
                self._state = ServerState.ERROR
                self._publish_state()

    @staticmethod
    def _spawn_kwargs() -> dict:
        if os.name == "nt":
            return {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            }
        return {"start_new_session": True}

    @staticmethod
    def _terminate(proc: asyncio.subprocess.Process) -> None:
        if os.name == "nt":
            with contextlib.suppress(OSError, ProcessLookupError):
                os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
                return
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()

    @staticmethod
    def _kill(proc: asyncio.subprocess.Process) -> None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()

    @staticmethod
    def _terminate_pid(pid: int) -> None:
        if os.name == "nt":
            with contextlib.suppress(OSError, ProcessLookupError):
                os.kill(pid, signal.CTRL_BREAK_EVENT)
                return
        with contextlib.suppress(ProcessLookupError, psutil.Error):
            psutil.Process(pid).terminate()

    @staticmethod
    def _port_from_args(args: list[str]) -> Optional[int]:
        for i, arg in enumerate(args):
            if arg in ("--port",) and i + 1 < len(args):
                with contextlib.suppress(ValueError):
                    return int(args[i + 1])
        return None

    @staticmethod
    def _pid_on_port(port: int) -> Optional[int]:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if (conn.laddr is not None and conn.laddr.port == port
                        and conn.status == psutil.CONN_LISTEN and conn.pid):
                    return conn.pid
        except (psutil.Error, OSError):
            pass
        return None

    @staticmethod
    async def _port_open(port: int) -> bool:
        def check() -> bool:
            with contextlib.suppress(OSError):
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    return True
            return False

        return await asyncio.to_thread(check)

    async def _detect_version(self) -> str:
        exe = self._get_config().resolved_exe()
        if not exe:
            return ""
        try:
            proc = await asyncio.create_subprocess_exec(
                exe, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                **self._spawn_kwargs(),
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            lines = [ln for ln in out.decode(errors="replace").splitlines() if ln.strip()]
            return lines[0] if lines else ""
        except (OSError, asyncio.TimeoutError):
            return ""
