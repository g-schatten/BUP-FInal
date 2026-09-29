"""Load test for the decision API (GET /api/alerts): the endpoint that runs the
full forecast -> detect -> allocate path per station/fuel on every call, so it's
the realistic worst case for latency under concurrency (Section 17).

No new dependency: httpx is already a backend requirement. Run from the host
against the running compose stack:  python3 loadtest/decision_api.py
"""

import asyncio
import statistics
import sys
import time

import httpx

BASE = "http://localhost:8080"
# NOTE: an earlier run at CONCURRENCY=20 saturated the simulator's own SQLAlchemy
# pool (size 5 + overflow 10 = 15 max connections) and required restarting the
# simulator container to recover — see README "Load testing" for the full finding.
# 8 stays comfortably under that ceiling.
CONCURRENCY = 8
DURATION_S = 15


async def worker(client: httpx.AsyncClient, deadline: float, latencies: list, errors: list):
    while time.monotonic() < deadline:
        t0 = time.monotonic()
        try:
            r = await client.get(f"{BASE}/api/alerts")
            latencies.append((time.monotonic() - t0) * 1000)
            if r.status_code >= 400:
                errors.append(r.status_code)
        except Exception as e:
            errors.append(str(e))


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(p * len(sorted_values)))
    return sorted_values[idx]


async def main():
    deadline = time.monotonic() + DURATION_S
    latencies: list[float] = []
    errors: list = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        await asyncio.gather(*[worker(client, deadline, latencies, errors) for _ in range(CONCURRENCY)])

    total = len(latencies) + len(errors)
    latencies.sort()
    print(f"path: GET /api/alerts, concurrency: {CONCURRENCY}, duration_s: {DURATION_S}")
    print(f"total_requests: {total}  errors: {len(errors)}  error_rate: {len(errors) / total:.3f}" if total else "no requests completed")
    if latencies:
        print(f"throughput_rps: {len(latencies) / DURATION_S:.1f}")
        print(f"avg_ms: {statistics.mean(latencies):.1f}")
        print(f"p50_ms: {percentile(latencies, 0.50):.1f}")
        print(f"p95_ms: {percentile(latencies, 0.95):.1f}")
        print(f"p99_ms: {percentile(latencies, 0.99):.1f}")
    if errors:
        print(f"sample errors: {errors[:5]}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
