# Security Policy

## Trust model — read this first

llama-monitor is a **single-user control panel for a `llama-server` on your own
machine** (or your own private network). It can launch programs, read your
models folder, and rewrite its own files, so it is designed to run on a trust
boundary you control — **not** as a public multi-tenant internet service.

What that means in practice:

- **Local by default.** New installs bind to `127.0.0.1:8000` — the panel is
  only reachable from the machine it runs on. `llama-server` is also bound to
  `127.0.0.1` by default.
- **Opt-in exposure, with a gate.** To reach the panel over the LAN / Tailscale
  you set `panel.host` to `0.0.0.0`. In that case you should set a **panel
  token**: every API, proxy and WebSocket request must then carry it. Binding a
  non-loopback address **without** a token is allowed but loudly warned — it is
  your choice, and it opens the door.
- **Host / Origin guard, even without a token.** Host and `Origin` /
  `Sec-Fetch-Site` headers are checked on every API, proxy and WebSocket
  request, which blocks DNS rebinding, CSRF and cross-site log streaming.
  Browserless clients (curl, OpenAI SDKs, the tray) are unaffected.
- **The preset's `--api-key` is caller-scoped.** The proxy injects your
  llama-server API key only for loopback callers or token-authenticated remote
  ones. An open (no-token) LAN caller never sees it and must supply its own
  `Authorization` header. The panel never forwards the panel token to
  `llama-server`.
- **Optional TLS.** Set `panel.tls_cert` / `panel.tls_key` to serve over HTTPS
  (also required to install the PWA over LAN / Tailscale).
- **Hardened update paths.** The panel self-update is `git merge --ff-only`
  (it never rewrites local work); the llama.cpp updater verifies every download
  against its declared size and the sha256 GitHub publishes for the asset (plus
  an optional user pin) and runs the build's `--version` before it is used. CI
  builds install from a hash-pinned lockfile with `--require-hashes`.

These are deliberate design boundaries, not hardening TODOs.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅ |

Only the **latest release** is supported. Fixes ship forward, not back to older
tags — run `git pull` (or the in-app **Update now**) to get them.

## Reporting a vulnerability

**Please report security issues privately**, not as a public issue:

- Use **Private vulnerability reporting** on the repository →
  [Report a vulnerability](https://github.com/Leo00703/llama-monitor/security/advisories/new)
  (GitHub Security Advisory).

Tell us what you found and how to reproduce it. We'll confirm, fix, and publish
a security advisory (with a Dependabot alert where applicable) before any public
disclosure.

### Not considered vulnerabilities

- A panel you deliberately bound to a non-loopback address **without** a token
  — that is the documented open-door option, warned at startup.
- Anything requiring you to hand someone physical/admin access to the machine
  already running the panel.
- A `llama-server` you started yourself (outside the panel) on a public address.

## Privacy of reports

When reporting (or filing any issue), scrub anything that identifies a person,
machine, or network — real local paths, hostnames / LAN IPs / `*.ts.net` names,
serial numbers, API keys, and full log lines (the `[panel] starting: …` line
contains the whole launch command, including model paths). Use placeholders.
See [`AGENTS.md`](AGENTS.md) → Privacy.
