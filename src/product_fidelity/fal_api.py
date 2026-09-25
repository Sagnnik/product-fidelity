"""One entry point for billable fal image calls in this project."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from product_fidelity.budget import reserve


def call(endpoint: str, arguments: dict[str, Any], *, width: int, height: int) -> dict[str, Any]:
    """Reserve the estimated charge, then submit one image request."""
    load_dotenv()
    if not os.getenv("FAL_KEY"):
        raise RuntimeError("FAL_KEY is missing. Run `product-fidelity configure-key` first.")
    if arguments.get("num_images", 1) != 1:
        raise ValueError("The budget guard supports one output image per request")
    reserve(endpoint, width, height)
    import fal_client

    return fal_client.subscribe(endpoint, arguments=arguments)
