"""What the operator approved, and why — joined onto the simulator's allocation ledger
for the decision-history view.

The simulator's /v1/allocations is the source of truth for what shipped and where it is
now; this only adds the context it was approved under (risk, expected impact, which
policy recommended it) and keeps rejected attempts, which never reach the ledger.
"""

import time
from collections import deque

# ponytail: in-memory — context for past decisions is lost on backend restart (the ledger
# itself survives in the simulator). Upgrade path: persist to SQLite if history must survive.
_by_allocation_id: dict[int, dict] = {}
_rejected: deque = deque(maxlen=50)


def record_applied(allocation_id: int, context: dict):
    _by_allocation_id[allocation_id] = {"approved_at": time.time(), **context}


def record_rejected(context: dict):
    _rejected.append({"attempted_at": time.time(), **context})


def context_for(allocation_id: int) -> dict | None:
    return _by_allocation_id.get(allocation_id)


def rejected_attempts() -> list[dict]:
    return list(reversed(_rejected))
