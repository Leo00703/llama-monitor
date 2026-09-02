/* llama-monitor service worker — PWA installability + offline shell.
 *
 * Strategy: network-first for everything on this origin, cache fallback —
 * but the network fetch is BOUNDED by a timeout. Unbounded is what froze
 * navigation (#57): while the panel is busy (e.g. mid-generation on a
 * saturated machine) a slow GET / kept the browser on the old page with
 * the loading bar and nothing interactive, because this fetch never
 * settled. With a bound, navigation always commits in a few seconds;
 * when the network is just slow, the cached shell loads and the app's
 * own REST/WS re-sync fills in the live data as it arrives.
 *
 * The cache is only a fallback (airplane mode / flaky LAN), never a
 * source of truth — so a panel update is picked up on the next load and
 * the installed app can never be stuck on stale JS.
 *
 * /api/*, /ws* and /v1/* are NEVER touched by the service worker:
 * live data (health, metrics, logs, proxied inference) always goes to
 * the network, and the app's own WS auto-reconnect handles outages.
 */
"use strict";

/* Bump the version whenever the shell must be re-cached from scratch.
   v2 (#58 era): the v1 cache could hold a MIXED shell (new index.html + old
   js/css after a deploy, since the browser disk cache had no explicit
   Cache-Control). The backend now sends no-cache on shell files; this bump
   wipes any stale v1 cache that is already out there. */
const CACHE = "llama-monitor-v2";
const SHELL = [
  "/",
  "/css/style.css",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
  "/fonts/geist-mono-latin.woff2",
  /* every script — the offline shell must boot the app, not just the HTML */
  "/js/api.js",
  "/js/ui.js",
  "/js/metrics.js",
  "/js/pages/dashboard.js",
  "/js/pages/models.js",
  "/js/pages/generation.js",
  "/js/pages/presets.js",
  "/js/pages/settings.js",
  "/js/pages/analytics.js",
  "/js/backend.js",
  "/js/update.js",
  "/js/app.js",
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

/* Hard bounds on how long we wait for the network before the cache wins.
   Navigation gets a bit more grace than sub-resources. */
const NAV_TIMEOUT = 4000;
const RES_TIMEOUT = 3000;

function timedFetch(req, ms, init) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  return fetch(req, { ...init, signal: ctrl.signal }).finally(() => clearTimeout(t));
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const p = url.pathname;
  if (p.startsWith("/api/") || p.startsWith("/ws") || p.startsWith("/v1/")) return;

  const timeout = req.mode === "navigate" ? NAV_TIMEOUT : RES_TIMEOUT;
  // Shell files must never be served stale from the browser's HTTP disk
  // cache (heuristic freshness): revalidate on every load — an etag
  // round-trip that is free on a LAN. Offline the revalidation fails and
  // the SW cache below wins, exactly as before.
  const cacheMode = req.mode === "navigate" ? { cache: "reload" } : { cache: "no-cache" };
  event.respondWith(
    timedFetch(req, timeout, cacheMode)
      .then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, clone));
        }
        return res;
      })
      .catch(async () => {
        const hit = await caches.match(req);
        if (hit) return hit;
        if (req.mode === "navigate") return caches.match("/");
        return Response.error();
      })
  );
});
