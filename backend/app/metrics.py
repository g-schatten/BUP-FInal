"""Hand-rolled Prometheus text-format counters — no prometheus_client dependency.
Covers all 3 observability layers from Section 14 with stdlib only:
  Application → http_requests_total, http_errors_total, http_request_duration_seconds_avg
  System      → process_cpu_seconds_total, process_max_rss_kb (stdlib `resource`, no new dep)
  Intelligence→ allocations_applied/rejected_total, alerts_active, integration_failures_total
"""

import resource

_values: dict[str, float] = {}
_latency_sum: dict[str, float] = {}
_latency_count: dict[str, int] = {}


def inc(name: str, value: float = 1):
    _values[name] = _values.get(name, 0) + value


def set_gauge(name: str, value: float):
    _values[name] = value


def observe_latency(name: str, seconds: float):
    _latency_sum[name] = _latency_sum.get(name, 0.0) + seconds
    _latency_count[name] = _latency_count.get(name, 0) + 1


def render_prometheus() -> str:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    system = {
        "process_cpu_seconds_total": usage.ru_utime + usage.ru_stime,
        "process_max_rss_kb": usage.ru_maxrss,  # kilobytes on Linux
    }
    lines = [f"{name} {value}\n" for name, value in sorted({**_values, **system}.items())]
    for name, total in sorted(_latency_sum.items()):
        count = _latency_count[name]
        lines.append(f"{name}_avg {total / count:.4f}\n")
        lines.append(f"{name}_count {count}\n")
    return "".join(lines)
