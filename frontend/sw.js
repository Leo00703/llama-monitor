/* llama-monitor service worker — PWA installability + offline shell.
 *
 * Strategy: network-first for everything on this origin, cache fallback.
 * The cache is only a fallback (airplane mode / flaky LAN), never a
 * source of truth — so a panel update is picked up on the next load and
 * the installed app can never be stuck on stale JS.
 *
 * /api/*, /ws* and /v1/* are NEVER touched by the service worker:
 * live data (health, metrics, logs, proxied inference) always goes to
 * the network, and the app's own WS auto-reconnect handles outages.
 */
"use strict";

const CACHE = "llama-monitor-v1";
const SHELL = [
  "/",
  "/css/style.css",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
  "/fonts/geist-mono-latin.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const p = url.pathname;
  if (p.startsWith("/api/") || p.startsWith("/ws") || p.startsWith("/v1/")) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, clone));
        }
        return res;
      })
      .catch(() =>
        caches.match(req).then(
          (hit) => hit || (req.mode === "navigate" ? caches.match("/") : Response.error())
        )
      )
  );
});
