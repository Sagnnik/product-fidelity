"""fal calls, cost estimates, and a small local run log."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Price snapshot from fal model pages, 2026-09-25.
PRICE_PER_MP = {
    "fal-ai/flux-1/dev": Decimal("0.025"),
    "fal-ai/flux-1/dev/image-to-image": Decimal("0.025"),
}
WIDTH = 768
HEIGHT = 1024
LOG_FILE = Path("logs/run.log")


def estimated_cost(endpoint: str, width: int, height: int) -> Decimal:
    return PRICE_PER_MP[endpoint] * max(1, math.ceil(width * height / 1_000_000))


def log_event(event: str, **details: Any) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    record = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **details}
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\n")


def reserved_spend() -> Decimal:
    if not LOG_FILE.exists():
        return Decimal("0")
    total = Decimal("0")
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["event"] == "request_reserved":
            total += Decimal(record["estimated_usd"])
    return total


def call(endpoint: str, arguments: dict[str, Any], *, width: int, height: int) -> dict[str, Any]:
    """Log estimated spend before submitting one image request."""
    load_dotenv()
    if not os.getenv("FAL_KEY"):
        raise RuntimeError("FAL_KEY is missing. Run `product-fidelity configure-key` first.")
    if arguments.get("num_images", 1) != 1:
        raise ValueError("Use one output image per request so the cost estimate stays accurate")
    cost = estimated_cost(endpoint, width, height)
    limit = Decimal(os.getenv("FAL_MAX_SPEND_USD", "8.00"))
    if reserved_spend() + cost > limit:
        raise RuntimeError(f"Estimated fal spend would exceed ${limit:.2f}")
    log_event("request_reserved", endpoint=endpoint, estimated_usd=str(cost))
    import fal_client

    try:
        result = fal_client.subscribe(endpoint, arguments=arguments)
    except Exception as error:
        log_event("request_failed", endpoint=endpoint, error=type(error).__name__)
        raise
    log_event("request_completed", endpoint=endpoint)
    return result
