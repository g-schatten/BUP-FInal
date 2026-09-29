"""Hand-rolled Prometheus text-format counters — no prometheus_client dependency.
A handful of gauges/counters is plenty for a hackathon observability bar;
pulling in the real client would be premature for this scope."""

_values: dict[str, float] = {}


def inc(name: str, value: float = 1):
    _values[name] = _values.get(name, 0) + value


def set_gauge(name: str, value: float):
    _values[name] = value


def render_prometheus() -> str:
    return "".join(f"{name} {value}\n" for name, value in sorted(_values.items()))
