"""Structured (JSON-line) logging to stdout — captured by `docker compose logs`.
No ELK/Loki wiring; stdout JSON lines satisfy the observability requirement's
"logs ... or equivalent outputs" bar without extra infra for a hackathon clock.
"""

import json
import logging
import sys
import time

_logger = logging.getLogger("fuel_platform")
_logger.setLevel(logging.INFO)
_logger.propagate = False
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)


def log_event(event: str, **fields):
    _logger.info(json.dumps({"ts": time.time(), "event": event, **fields}))
