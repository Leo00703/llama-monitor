"""parallel-test.py — does this llama-server really serve concurrent chats?

Fires N simultaneous streaming /v1/chat/completions requests directly at the
server (no UI, no panel proxy) and measures whether they run in parallel.

Usage:  python parallel-test.py http://127.0.0.1:8080 [N]     (default N = 2)

Verdict:
  ratio ~0.5 with N=2  -> fully parallel (server OK — a UI/client problem)
  ratio ~1.0           -> serialized (server is single-slot or stalling)
"""
import json
import sys
import time
import urllib.request
import concurrent.futures

def one_request(base, i):
    body = json.dumps({
        "model": "local",
        "messages": [{"role": "user",
                      "content": f"Reply with exactly one short sentence mentioning the number {i}."}],
        "max_tokens": 60,
        "temperature": 0,
        "stream": True,
    }).encode()
    req = urllib.request.Request(
        base + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    first = None
    chunks = 0
    status = None
    err = None
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            status = r.status
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    d = json.loads(line[6:])
                    delta = (d.get("choices") or [{}])[0].get("delta", {})
                    if delta.get("content"):
                        chunks += 1
                        if first is None:
                            first = time.monotonic() - t0
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    return dict(i=i, dt=time.monotonic() - t0, first=first, chunks=chunks,
                status=status, err=err)

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    # health + live slot count (the /slots endpoint is the ground truth)
    try:
        with urllib.request.urlopen(base + "/health", timeout=10) as r:
            print(f"health: {r.read().decode().strip()}")
    except Exception as e:
        print(f"health check failed: {e}  (is the URL right? include the port)")
        return 2
    try:
        with urllib.request.urlopen(base + "/slots", timeout=10) as r:
            data = json.loads(r.read().decode())
            slots = data.get("slots", data) if isinstance(data, dict) else data
            busy = sum(1 for s in slots if s.get("idle") is False)
            print(f"server: {len(slots)} slot(s) live, {busy} busy  <- the ground truth")
    except Exception as e:
        print(f"warning: /slots not readable ({e})")

    # warm-up (loads model into slot, JIT, etc.)
    print(f"\nwarm-up request ...")
    w = one_request(base, 0)
    print(f"  warm-up: {w['dt']:.1f}s  chunks={w['chunks']}  {w['err'] or 'ok'}")
    if w["err"]:
        print(f"request failed: {w['err']}")
        return 2

    print(f"\nfiring {n} concurrent streaming chats ...")
    t0 = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
        results = list(ex.map(lambda i: one_request(base, i), range(1, n + 1)))
    wall = time.monotonic() - t0

    for r in results:
        ft = f"first-token {r['first']:.1f}s" if r["first"] else "no tokens"
        print(f"  req {r['i']}: {r['dt']:.1f}s  {ft}  chunks={r['chunks']}  {r['err'] or ''}")

    ok = all(r["err"] is None and r["chunks"] > 0 for r in results)
    s = sum(r["dt"] for r in results)
    # Judge by wall vs ONE request's time: parallel wall ≈ 1x, serialized
    # wall ≈ Nx. (wall/sum is misleading: it counts queue wait inside every
    # request, so even fully serialized N=2 only reaches 0.67.)
    r = wall / w["dt"] if w["dt"] > 0 else 0
    print(f"\nwall = {wall:.1f}s   one request = {w['dt']:.1f}s   "
          f"wall/one = {r:.2f}   (sum = {s:.1f}s)")
    if not ok:
        print("VERDICT: FAIL - some requests errored or produced no tokens (see server log)")
        return 1
    if r < 1.5:
        print(f"VERDICT: PARALLEL - the server runs {n} chats at once. "
              "If the web UI still queues, the problem is the UI/client, not the server.")
        return 0
    if r > n * 0.75:
        print("VERDICT: SERIALIZED - requests wait for each other. "
              "Check the startup log line 'n_slots = N' in the panel: if N is 1, "
              "set Parallel slots = 4 in the preset and hit Restart.")
        return 1
    print("VERDICT: PARTIAL - some overlap but not full parallelism "
          "(slot stalls or queueing; capture the server log during the test)")
    return 1

if __name__ == "__main__":
    sys.exit(main())
