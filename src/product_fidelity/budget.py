"""Conservative, local spending reservations for supported fal endpoints."""

from __future__ import annotations

import fcntl
import json
import math
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


# Price snapshot: 2026-09-25. Check fal's model pages before running a batch.
PRICE_PER_MP = {
    "fal-ai/flux-1/dev": Decimal("0.025"),
    "fal-ai/flux-1/dev/image-to-image": Decimal("0.025"),
    "fal-ai/flux-pro/v1/fill": Decimal("0.050"),
}
DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 1024
DEFAULT_MAX_SPEND = Decimal("8.00")


def estimated_cost(endpoint: str, width: int, height: int) -> Decimal:
    if endpoint not in PRICE_PER_MP:
        raise ValueError(f"Unpriced endpoint: {endpoint}")
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    billed_mp = max(1, math.ceil(width * height / 1_000_000))
    return PRICE_PER_MP[endpoint] * billed_mp


@dataclass(frozen=True)
class Reservation:
    endpoint: str
    estimated_usd: str
    total_reserved_usd: str


def reserve(
    endpoint: str,
    width: int,
    height: int,
    *,
    ledger_path: Path = Path(".usage/fal-ledger.json"),
    max_spend: Decimal | None = None,
) -> Reservation:
    """Reserve estimated cost before a request. Failed requests stay reserved."""
    cost = estimated_cost(endpoint, width, height)
    limit = max_spend or Decimal(os.getenv("FAL_MAX_SPEND_USD", "8.00"))
    if limit <= 0:
        raise ValueError("FAL_MAX_SPEND_USD must be positive")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(ledger_path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as ledger:
        fcntl.flock(ledger.fileno(), fcntl.LOCK_EX)
        ledger.seek(0)
        contents = ledger.read()
        data = json.loads(contents) if contents else {"reserved_usd": "0", "requests": []}
        total = Decimal(data["reserved_usd"]) + cost
        if total > limit:
            raise RuntimeError(
                f"Estimated fal budget exceeded: ${total:.3f} would exceed ${limit:.2f}"
            )
        data["reserved_usd"] = str(total)
        data["requests"].append(
            {"endpoint": endpoint, "width": width, "height": height, "estimated_usd": str(cost)}
        )
        ledger.seek(0)
        json.dump(data, ledger, indent=2)
        ledger.truncate()
        ledger.flush()
        os.fsync(ledger.fileno())
        return Reservation(endpoint, str(cost), str(total))
