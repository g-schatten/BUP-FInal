"""Structured (JSON-line) logging to stdout — captured by `docker compose logs`.
No ELK/Loki wiring; stdout JSON lines satisfy the observability requirement's
"logs ... or equivalent outputs" bar without extra infra for a hackathon clock.

Every event is also kept in a small in-memory ring buffer so the dashboard's
system-alerts view can show recent failures/recoveries without a log store.
"""

import json
import logging
import sys
import time
from collections import deque

_logger = logging.getLogger("fuel_platform")
_logger.setLevel(logging.INFO)
_logger.propagate = False
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)

# ponytail: in-memory, so recent activity resets on backend restart. The simulator's own
# /admin/audit is the durable record; upgrade path is a real log store (Loki/ELK).
_recent: deque = deque(maxlen=100)


def log_event(event: str, **fields):
    record = {"ts": time.time(), "event": event, **fields}
    _recent.append(record)
    _logger.info(json.dumps(record))


def recent_events() -> list[dict]:
    return list(reversed(_recent))
