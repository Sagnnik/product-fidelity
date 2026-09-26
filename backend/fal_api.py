from __future__ import annotations

import math
import os
import re
import threading
import fcntl
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Price snapshot from fal model pages, 2026-09-25.
PRICE_PER_MP = {
    "fal-ai/flux-1/dev": Decimal("0.025"),
    "fal-ai/flux-1/dev/image-to-image": Decimal("0.025"),
    "fal-ai/flux-2-pro": Decimal("0.030"),
}
WIDTH = 768
HEIGHT = 1024
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
DATA_ROOT = Path(
    os.getenv("STILLROOM_DATA_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or PROJECT_ROOT
).resolve()
LOG_FILE = DATA_ROOT / "LOGS.md"
LOCK_FILE = DATA_ROOT / ".fal_call.lock"
CALL_LOCK = threading.Lock()


def site_fal_key() -> str | None:
    return os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")


def load_fal_key() -> bool:
    return bool(site_fal_key())


def estimated_cost(endpoint: str, width: int, height: int, *, input_images: int = 1) -> Decimal:
    if endpoint == "fal-ai/flux-2-pro/edit":
        # Both references are prepared below 1 MP. Reserve conservatively above
        # fal's listed output and input MP pricing, including failed requests.
        return Decimal("0.060") + Decimal("0.015") * max(0, input_images - 1)
    return PRICE_PER_MP[endpoint] * max(1, math.ceil(width * height / 1_000_000))


def log_event(event: str, **details: Any) -> None:
    time = datetime.now(timezone.utc).isoformat(timespec="seconds")
    detail_text = ", ".join(f"{key}={value}" for key, value in details.items())
    line = f"- {time} {event}: {detail_text}"
    if event == "request_reserved":
        line += f" <!-- fal:reserved_usd={details['estimated_usd']} -->"
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(line + "\n")


def reserved_spend() -> Decimal:
    if not LOG_FILE.exists():
        return Decimal("0")
    charges = re.findall(r"<!-- fal:reserved_usd=([0-9.]+) -->", LOG_FILE.read_text(encoding="utf-8"))
    return sum((Decimal(charge) for charge in charges), Decimal("0"))


def call(endpoint: str, arguments: dict[str, Any], *, width: int, height: int, fal_key: str | None = None) -> dict[str, Any]:
    """Log estimated spend before submitting one image request."""
    key = fal_key or site_fal_key()
    if not key:
        raise RuntimeError("fal key is missing")
    if arguments.get("num_images", 1) != 1:
        raise ValueError("Use one output image per request so the cost estimate stays accurate")
    cost = estimated_cost(endpoint, width, height, input_images=len(arguments.get("image_urls", [None])))
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    with CALL_LOCK, LOCK_FILE.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        limit = Decimal(os.getenv("FAL_MAX_SPEND_USD", "8.00"))
        if fal_key is None and reserved_spend() + cost > limit:
            raise RuntimeError(f"Estimated fal spend would exceed ${limit:.2f}")
        log_event("request_reserved_byok" if fal_key else "request_reserved", endpoint=endpoint, estimated_usd=str(cost))
        import fal_client

        try:
            result = fal_client.SyncClient(key=key).subscribe(endpoint, arguments=arguments)
        except Exception as error:
            log_event("request_failed", endpoint=endpoint, error=type(error).__name__)
            raise
        log_event("request_completed", endpoint=endpoint)
        return result
