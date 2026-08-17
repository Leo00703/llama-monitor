"""HTTP proxy to the running llama-server (plan 4.7/4.9).

Forwards /proxy/* requests to http://127.0.0.1:<port>/*, injecting the
preset's saved generation defaults into request bodies. Fields explicitly
present in the request body always win over saved defaults (setdefault).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Callable, Optional

import httpx

log = logging.getLogger("llama-monitor.proxy")

PROPS_TTL = 60.0

# paths where generation defaults are injected
INJECT_PATHS = {"completion", "v1/chat/completions"}

# request fields a server accepts even though /props may not list them
EXTRA_FIELDS = {
    "stop", "grammar", "json_schema", "logit_bias", "dry_sequence_breakers",
    "cache_prompt", "n_return_sequences", "add_bos", "add_eos",
}

PROXY_SKIP_REQUEST_HEADERS = {
    "host", "content-length", "connection", "accept-encoding", "keep-alive",
    "upgrade", "transfer-encoding", "te", "trailer", "proxy-authorization",
    "proxy-authenticate", "authorization", "content-type",
}

PROXY_SKIP_RESPONSE_HEADERS = {
    "content-encoding", "content-length", "transfer-encoding",
    "connection", "keep-alive",
}

REQUEST_TIMEOUT = httpx.Timeout(600.0, connect=10.0)
STREAM_TIMEOUT = httpx.Timeout(None, connect=10.0)
PROPS_TIMEOUT = httpx.Timeout(5.0, connect=2.0)


class ProxyOffline(Exception):
    """Raised when no llama-server port is known or it cannot be reached."""


class ServerProxy:
    def __init__(
        self,
        get_port: Callable[[], Optional[int]],
        get_launch: Callable[[], Optional[dict[str, Any]]],
    ) -> None:
        self._get_port = get_port
        self._get_launch = get_launch
        self._params: Optional[dict[str, Any]] = None
        self._params_at: float = 0.0

    # ------------------------------------------------------------------
    # live server params (for the defaults UI + injection allow-list)
    # ------------------------------------------------------------------

    def base_url(self) -> Optional[str]:
        port = self._get_port()
        if port is None:
            return None
        return f"http://127.0.0.1:{port}"

    async def server_params(self) -> Optional[dict[str, Any]]:
        """default_generation_settings.params from the live server, cached."""
        base = self.base_url()
        if base is None:
            return None
        now = time.monotonic()
        if self._params is not None and now - self._params_at < PROPS_TTL:
            return self._params
        try:
            async with httpx.AsyncClient(timeout=PROPS_TIMEOUT) as client:
                resp = await client.get(f"{base}/props")
                resp.raise_for_status()
                data = resp.json()
            params = data.get("default_generation_settings", {}).get("params")
            self._params = params if isinstance(params, dict) else None
            self._params_at = now
            return self._params
        except Exception:
            # keep serving stale params while the server is unreachable
            return self._params

    def invalidate_props_cache(self) -> None:
        self._params = None
        self._params_at = 0.0

    # ------------------------------------------------------------------
    # request plumbing
    # ------------------------------------------------------------------

    def _saved_generation(self) -> dict[str, Any]:
        launch = self._get_launch() or {}
        gen = launch.get("generation")
        return gen if isinstance(gen, dict) else {}

    async def _injected(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if path not in INJECT_PATHS:
            return body
        out = dict(body)
        saved = self._saved_generation()
        if not saved:
            return out
        params = await self.server_params()
        known = (set(params) | EXTRA_FIELDS) if params else None
        for key, value in saved.items():
            if key in out:
                continue  # explicit request field wins
            if known is not None and key not in known:
                continue  # this server build does not know the field
            out[key] = value
        return out

    def _forward_headers(self, headers: dict[str, str]) -> dict[str, str]:
        fwd = {
            k: v for k, v in headers.items()
            if k.lower() not in PROXY_SKIP_REQUEST_HEADERS
        }
        launch = self._get_launch() or {}
        api_key = (launch.get("api_key") or "").strip()
        if api_key:
            fwd["authorization"] = f"Bearer {api_key}"
        return fwd

    async def request(
        self,
        method: str,
        path: str,
        body: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        query: str = "",
    ) -> tuple[int, dict[str, str], bytes]:
        """Non-streaming forward. Returns (status, headers, content)."""
        base = self.base_url()
        if base is None:
            raise ProxyOffline("llama-server is not running")
        path = path.lstrip("/")
        if body is not None:
            body = await self._injected(path, body)
            headers = {**(headers or {}), "content-type": "application/json"}
        url = f"{base}/{path}" + (f"?{query}" if query else "")
        content = json.dumps(body).encode() if body is not None else None
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.request(
                    method, url, content=content,
                    headers=self._forward_headers(headers or {}),
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProxyOffline(str(exc)) from exc
        out_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in PROXY_SKIP_RESPONSE_HEADERS
        }
        return resp.status_code, out_headers, resp.content

    async def stream(
        self,
        method: str,
        path: str,
        body: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        query: str = "",
    ) -> AsyncIterator[bytes]:
        """Streaming forward (SSE). Yields raw body chunks."""
        base = self.base_url()
        if base is None:
            raise ProxyOffline("llama-server is not running")
        path = path.lstrip("/")
        if body is not None:
            body = await self._injected(path, body)
            headers = {**(headers or {}), "content-type": "application/json"}
        url = f"{base}/{path}" + (f"?{query}" if query else "")
        content = json.dumps(body).encode() if body is not None else None
        client = httpx.AsyncClient(timeout=STREAM_TIMEOUT)
        try:
            req = client.build_request(method, url, content=content,
                                       headers=self._forward_headers(headers or {}))
            resp = await client.send(req, stream=True)
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise ProxyOffline(str(exc)) from exc
        finally:
            await client.aclose()
