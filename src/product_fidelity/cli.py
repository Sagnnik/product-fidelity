"""Setup and cost planning commands. These commands make no paid fal calls."""

from __future__ import annotations

import argparse
import getpass
import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from product_fidelity.fal_api import HEIGHT, WIDTH, estimated_cost, log_event, reserved_spend


def configure_key() -> None:
    target = Path(".env")
    if target.exists():
        raise SystemExit(".env already exists. Edit it locally if you need to change the key.")
    key = getpass.getpass("Paste your fal API key (input is hidden): ").strip()
    if not key or "\n" in key or "\r" in key:
        raise SystemExit("A single-line fal API key is required.")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as env_file:
        env_file.write(f"FAL_KEY={key}\nFAL_MAX_SPEND_USD=8.00\n")
    print("Saved .env with owner-only permissions. It is ignored by Git.")


def doctor() -> None:
    load_dotenv()
    key_state = "present" if os.getenv("FAL_KEY") else "missing"
    log_event("setup_checked", fal_key=key_state)
    print("fal key:", key_state)
    print("spend limit: $" + os.getenv("FAL_MAX_SPEND_USD", "8.00"))
    print(f"estimated spend: ${reserved_spend():.2f}")
    print("run log: logs/run.log")


def plan(products: int, prompts: int, seeds: int, width: int, height: int) -> None:
    if min(products, prompts, seeds, width, height) <= 0:
        raise SystemExit("Counts and dimensions must be positive")
    cases = products * prompts * seeds
    # The preserved-product method generates a background with the text model.
    endpoints = (
        "fal-ai/flux-1/dev",
        "fal-ai/flux-1/dev/image-to-image",
        "fal-ai/flux-1/dev",
    )
    total = cases * sum((estimated_cost(endpoint, width, height) for endpoint in endpoints), Decimal())
    print(f"{cases} cases x {len(endpoints)} methods = {cases * len(endpoints)} paid images")
    print(f"{width}x{height} px; estimated model cost: ${total:.2f}")
    print("Prices are estimates from 2026-09-25; verify current fal pricing before a batch.")
    if total > Decimal(os.getenv("FAL_MAX_SPEND_USD", "8.00")):
        raise SystemExit("Planned cost exceeds FAL_MAX_SPEND_USD")


def main() -> None:
    parser = argparse.ArgumentParser(description="Product fidelity experiment setup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("configure-key", help="Save a fal key without echoing it")
    subparsers.add_parser("doctor", help="Check setup without showing the key")
    planner = subparsers.add_parser("plan", help="Estimate costs before generation")
    planner.add_argument("--products", type=int, default=4)
    planner.add_argument("--prompts", type=int, default=3)
    planner.add_argument("--seeds", type=int, default=1)
    planner.add_argument("--width", type=int, default=WIDTH)
    planner.add_argument("--height", type=int, default=HEIGHT)
    args = parser.parse_args()
    if args.command == "configure-key":
        configure_key()
    elif args.command == "doctor":
        doctor()
    else:
        load_dotenv()
        plan(args.products, args.prompts, args.seeds, args.width, args.height)


if __name__ == "__main__":
    main()
