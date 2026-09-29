"""Shared-token guard for actions that change the world (shipments, simulator control).

Set OPERATOR_TOKEN to require it; unset (local dev) leaves these actions open. Reads
stay public — the dashboard is view-only without the token.
"""

import os
import secrets

from fastapi import Header, HTTPException

OPERATOR_TOKEN = os.environ.get("OPERATOR_TOKEN", "")


def auth_required() -> bool:
    return bool(OPERATOR_TOKEN)


async def require_operator(x_operator_token: str | None = Header(default=None)):
    if OPERATOR_TOKEN and not secrets.compare_digest(x_operator_token or "", OPERATOR_TOKEN):
        raise HTTPException(401, "operator token required")
