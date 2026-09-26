from __future__ import annotations

import io
import json
import math
import shutil
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from backend.fal_api import DATA_ROOT, estimated_cost, load_fal_key, log_event, reserved_spend, site_fal_key

ROOT = DATA_ROOT / "outputs" / "campaigns"
ENDPOINT = "fal-ai/flux-2-pro/edit"
WIDTH, HEIGHT = 768, 1024
SEED = 20260925
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_BATCH_IMAGES = 10
Image.MAX_IMAGE_PIXELS = 30_000_000
MANIFEST_LOCK = threading.Lock()

SCENES = [
    {
        "id": "studio",
        "name": "Studio",
        "setting": "a warm cream studio sweep with soft daylight from the upper left, a clear surface, and a believable contact shadow",
        "detail": "Clean product focus",
    },
    {
        "id": "lifestyle",
        "name": "Lifestyle",
        "setting": "a sunlit contemporary café tabletop, warm natural materials, softly blurred background, and realistic contact with the table",
        "detail": "A product in context",
    },
    {
        "id": "celebration",
        "name": "Celebration",
        "setting": "a refined festive tabletop with warm golden bokeh and a few restrained decorative accents behind the product, realistic contact shadow",
        "detail": "Seasonal campaign mood",
    },
]
ISSUES = {"shape", "color", "label", "lighting", "artifact", "scene", "extra_product"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def campaign_dir(campaign_id: str) -> Path:
    if len(campaign_id) != 12 or any(c not in "0123456789abcdef" for c in campaign_id):
        raise ValueError("Unknown campaign")
    path = ROOT / campaign_id
    if not path.is_dir():
        raise ValueError("Unknown campaign")
    return path


def read_campaign(campaign_id: str) -> dict[str, Any]:
    return json.loads((campaign_dir(campaign_id) / "manifest.json").read_text(encoding="utf-8"))


def read_owned_campaign(campaign_id: str, user_id: str) -> dict[str, Any]:
    manifest = read_campaign(campaign_id)
    if manifest.get("owner_user_id") != user_id:
        raise ValueError("Unknown campaign")
    return manifest


def update_campaign(campaign_id: str, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    with MANIFEST_LOCK:
        manifest = read_campaign(campaign_id)
        change(manifest)
        path = campaign_dir(campaign_id) / "manifest.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return manifest


def prepare_reference(raw: bytes, target: Path) -> tuple[str, str]:
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose an image smaller than 10 MB")
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError("Choose a valid JPEG, PNG, or WebP image") from error
    if image.format not in {"JPEG", "PNG", "WEBP"}:
        raise ValueError("Choose a JPEG, PNG, or WebP image")
    if min(image.size) < 300:
        raise ValueError("Choose a product photo at least 300 pixels on each side")
    extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[image.format]
    original_name = f"source_original.{extension}"
    (target / original_name).write_bytes(raw)
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((650, 700), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "#faf9f6")
    position = ((WIDTH - image.width) // 2, 240 + (700 - image.height) // 2)
    canvas.paste(image, position)
    canvas.save(target / "reference.png")
    return original_name, "reference.png"


def prepare_background(raw: bytes, target: Path) -> str:
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a background image smaller than 10 MB")
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError("Choose a valid background JPEG, PNG, or WebP image") from error
    if image.format not in {"JPEG", "PNG", "WEBP"} or min(image.size) < 300:
        raise ValueError("Choose a background JPEG, PNG, or WebP at least 300 pixels on each side")
    extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[image.format]
    (target / f"background_original.{extension}").write_bytes(raw)
    image = ImageOps.exif_transpose(image).convert("RGB")
    ImageOps.fit(image, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS).save(target / "background.png")
    return "background.png"


def make_prompt(product: str, audience: str, critical_details: str, scene: dict[str, str], *, background_reference: bool = False) -> str:
    audience_text = f"The intended audience is {audience}. " if audience else ""
    details_text = f"Critical details to match: {critical_details}. " if critical_details else ""
    background_text = (
        "Use image 2 as the visual reference for the background and setting; place the product from image 1 into that scene. "
        if background_reference else ""
    )
    return (
        f"Create a premium photorealistic mobile portrait campaign photograph for {product}. "
        f"Use the product in image 1 as the only product. {background_text}Keep its shape, color, material, "
        f"and any existing markings as faithful as possible. Leave unmarked surfaces blank; never add "
        f"a new logo, label, or lettering. Do not place another product in the background, even blurred. "
        f"{details_text}Place it in {scene['setting']}. {audience_text}"
        "Leave quiet negative space in the upper quarter for a later ad headline. "
        "No overlaid text, extra products, people, or watermarks."
    )


def scene_rows(manifest: dict[str, Any], start: int, count: int) -> list[dict[str, Any]]:
    custom = manifest.get("scene_description", "")
    if custom:
        scenes = [{"id": "custom", "name": "Custom scene", "detail": "Your background direction", "setting": custom}]
    elif manifest.get("background_file"):
        scenes = [{"id": "background", "name": "Your background", "detail": "Based on your photo", "setting": "the setting shown in image 2"}]
    else:
        scenes = SCENES
    rows = []
    for index in range(start, start + count):
        preset = scenes[index % len(scenes)]
        repeat = index // len(scenes) + 1
        scene_id = preset["id"] if repeat == 1 else f"{preset['id']}_{repeat}"
        name = preset["name"] if repeat == 1 else f"{preset['name']} {repeat}"
        rows.append({
            "id": scene_id, "name": name, "detail": preset["detail"],
            "prompt": make_prompt(manifest["product"], manifest["audience"], manifest["critical_details"], preset,
                                  background_reference=bool(manifest.get("background_file"))),
            "status": "queued", "file": None, "generation_seconds": None,
            "review": "pending", "issues": [], "reviewed_at": None,
        })
    return rows


def start_campaign(
    raw: bytes, product: str, audience: str, critical_details: str = "",
    *, owner_user_id: str, funding: str, image_count: int = 3,
    scene_description: str = "", background_raw: bytes | None = None,
) -> dict[str, Any]:
    product, audience, critical_details, scene_description = (
        product.strip(), audience.strip(), critical_details.strip(), scene_description.strip()
    )
    if not 3 <= len(product) <= 120:
        raise ValueError("Describe the product in 3–120 characters")
    if len(audience) > 100:
        raise ValueError("Keep the audience note under 100 characters")
    if len(critical_details) > 180:
        raise ValueError("Keep critical product details under 180 characters")
    if len(scene_description) > 400:
        raise ValueError("Keep the scene description under 400 characters")
    if not 1 <= image_count <= MAX_BATCH_IMAGES:
        raise ValueError("Choose between 1 and 10 images per batch")
    if funding not in {"free", "byok"}:
        raise ValueError("Unknown funding mode")
    if funding == "free" and not load_fal_key():
        raise ValueError("fal key is missing; configure it in the local .env file")
    ROOT.mkdir(parents=True, exist_ok=True)
    campaign_id = uuid.uuid4().hex[:12]
    target = ROOT / campaign_id
    target.mkdir()
    try:
        original, reference = prepare_reference(raw, target)
        background_file = prepare_background(background_raw, target) if background_raw is not None else None
    except Exception:
        shutil.rmtree(target)
        raise
    manifest = {
        "id": campaign_id,
        "status": "queued",
        "created_at": now(),
        "created_epoch": time.time(),
        "product": product,
        "audience": audience,
        "critical_details": critical_details,
        "scene_description": scene_description,
        "background_file": background_file,
        "owner_user_id": owner_user_id,
        "funding": funding,
        "source_file": original,
        "reference_file": reference,
        "model_id": ENDPOINT,
        "seed": SEED,
        "size": [WIDTH, HEIGHT],
        "estimated_reserved_usd": 0.0,
        "first_preview_seconds": None,
        "scenes": [],
    }
    manifest["scenes"] = scene_rows(manifest, 0, image_count)
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log_event("campaign_created", campaign_id=campaign_id, scenes=image_count, model=ENDPOINT, funding=funding)
    return manifest


def add_images(campaign_id: str, count: int) -> dict[str, Any]:
    if not 1 <= count <= MAX_BATCH_IMAGES:
        raise ValueError("Choose between 1 and 10 images per batch")
    def add(manifest: dict[str, Any]) -> None:
        if manifest["status"] not in {"completed", "failed", "interrupted"}:
            raise ValueError("Wait for the current batch to finish")
        if manifest["funding"] == "free":
            if len(manifest["scenes"]) + count > MAX_BATCH_IMAGES:
                raise ValueError("Project-funded campaigns allow up to 10 images in total")
            if manifest["status"] == "failed" and manifest["estimated_reserved_usd"] == 0:
                raise ValueError("This campaign did not use its free allowance. Start a new campaign.")
        manifest["scenes"].extend(scene_rows(manifest, len(manifest["scenes"]), count))
        manifest["status"] = "queued"
        manifest.pop("error", None)
    return update_campaign(campaign_id, add)


def recover_interrupted_campaigns() -> None:
    """Reconcile files after a restart, without submitting any fal requests."""
    if not ROOT.exists():
        return
    for path in ROOT.glob("*/manifest.json"):
        try:
            campaign_id = path.parent.name
            manifest = read_campaign(campaign_id)
            if manifest["status"] not in {"queued", "running"}:
                continue

            def recover(item: dict[str, Any]) -> None:
                for scene in item["scenes"]:
                    if scene["status"] != "running":
                        continue
                    filename = f"{scene['id']}.png"
                    if (path.parent / filename).is_file():
                        scene.update(status="completed", file=filename)
                    else:
                        # The paid request may have succeeded. Never submit it again here.
                        scene["status"] = "interrupted"
                item["status"] = "interrupted"
                item["error"] = "Generation was interrupted. Continue only the images still waiting; an interrupted image may have been billed."

            update_campaign(campaign_id, recover)
            log_event("campaign_interrupted", campaign_id=campaign_id)
        except (OSError, ValueError, KeyError):
            continue


def resume_queued_campaign(campaign_id: str) -> dict[str, Any]:
    def resume(item: dict[str, Any]) -> None:
        if item["status"] not in {"interrupted", "failed"}:
            raise ValueError("This campaign is not waiting for recovery")
        if not any(scene["status"] == "queued" for scene in item["scenes"]):
            raise ValueError("No unsubmitted images remain. Add images to make a new request.")
        item["status"] = "queued"
        item.pop("error", None)
    return update_campaign(campaign_id, resume)


def download_image(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "product-fidelity-studio/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise RuntimeError("Generated image exceeded the 20 MB limit")
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    if image.size != (WIDTH, HEIGHT):
        raise RuntimeError(f"Unexpected generated size: {image.size}")
    temporary = destination.with_suffix(".tmp")
    image.save(temporary, format="PNG")
    temporary.replace(destination)


def make_contact_sheet(campaign_id: str) -> None:
    manifest = read_campaign(campaign_id)
    target = campaign_dir(campaign_id)
    items = [("SOURCE", "reference.png")] + [
        (scene["name"].upper(), scene["file"])
        for scene in manifest["scenes"] if scene["file"]
    ][:21]
    thumb_size = (288, 384)
    columns = min(4, len(items))
    grid = Image.new("RGB", (columns * thumb_size[0], math.ceil(len(items) / columns) * (thumb_size[1] + 46)), "#f7f5ef")
    draw = ImageDraw.Draw(grid)
    for index, (name, file) in enumerate(items):
        x = index % columns * thumb_size[0]
        y = index // columns * (thumb_size[1] + 46)
        image = Image.open(target / file).convert("RGB")
        image = ImageOps.fit(image, thumb_size)
        grid.paste(image, (x, y + 46))
        draw.text((x + 14, y + 16), name, fill="#1c2929")
    grid.save(target / "contact_sheet.jpg", quality=88)


def generate_campaign(campaign_id: str, fal_key: str | None = None) -> None:
    import fal_client
    from backend.fal_api import call

    target = campaign_dir(campaign_id)
    started = time.monotonic()
    update_campaign(campaign_id, lambda m: m.update(status="running", started_at=now()))
    try:
        key = fal_key or site_fal_key()
        if not key:
            raise RuntimeError("fal key is missing")
        source_url = fal_client.SyncClient(key=key).upload_file(str(target / "reference.png"))
        background_file = read_campaign(campaign_id).get("background_file")
        image_urls = [source_url]
        if background_file:
            image_urls.append(fal_client.SyncClient(key=key).upload_file(str(target / background_file)))
        for scene in read_campaign(campaign_id)["scenes"]:
            if scene["status"] != "queued":
                continue
            scene_id = scene["id"]
            def mark_running(m: dict[str, Any]) -> None:
                next(s for s in m["scenes"] if s["id"] == scene_id)["status"] = "running"
            update_campaign(campaign_id, mark_running)
            spend_before = reserved_spend()
            call_started = time.monotonic()
            try:
                result = call(ENDPOINT, {
                    "prompt": scene["prompt"], "image_urls": image_urls,
                    "image_size": {"width": WIDTH, "height": HEIGHT},
                    "seed": SEED, "output_format": "png",
                }, width=WIDTH, height=HEIGHT, fal_key=fal_key)
                filename = f"{scene_id}.png"
                download_image(result["images"][0]["url"], target / filename)
                elapsed = round(time.monotonic() - call_started, 2)
                delta = float(estimated_cost(ENDPOINT, WIDTH, HEIGHT, input_images=len(image_urls))) if fal_key else float(reserved_spend() - spend_before)
                def mark_done(m: dict[str, Any]) -> None:
                    row = next(s for s in m["scenes"] if s["id"] == scene_id)
                    row.update(status="completed", file=filename, generation_seconds=elapsed, returned_seed=result.get("seed"))
                    m["estimated_reserved_usd"] = round(m["estimated_reserved_usd"] + delta, 3)
                    if m["first_preview_seconds"] is None:
                        m["first_preview_seconds"] = round(time.monotonic() - started, 2)
                update_campaign(campaign_id, mark_done)
                log_event("campaign_image_saved", campaign_id=campaign_id, scene=scene_id, seconds=elapsed)
            except Exception:
                delta = float(estimated_cost(ENDPOINT, WIDTH, HEIGHT, input_images=len(image_urls))) if fal_key else float(reserved_spend() - spend_before)
                def mark_failed(m: dict[str, Any]) -> None:
                    next(s for s in m["scenes"] if s["id"] == scene_id)["status"] = "failed"
                    m["estimated_reserved_usd"] = round(m["estimated_reserved_usd"] + delta, 3)
                update_campaign(campaign_id, mark_failed)
                raise
    except Exception as error:
        from backend.quota import release_free_campaign
        manifest = read_campaign(campaign_id)
        if manifest.get("funding") == "free" and manifest.get("estimated_reserved_usd", 0) == 0:
            release_free_campaign(manifest["owner_user_id"])
        message = (
            "Your fal key was rejected. Check the key and try a new campaign."
            if fal_key and getattr(error, "status_code", None) in {401, 403}
            else "The studio's free budget is exhausted. Use your own fal key to continue."
            if "Estimated fal spend would exceed" in str(error)
            else "fal declined this prompt or image. Try another product description or source photo."
            if "content_policy_violation" in str(error)
            else "Generation stopped. Completed scenes are saved; ask the studio owner to check the run log."
        )
        update_campaign(campaign_id, lambda m: m.update(status="failed", error=message, finished_at=now()))
        if any(scene["file"] for scene in read_campaign(campaign_id)["scenes"]):
            make_contact_sheet(campaign_id)
        log_event("campaign_failed", campaign_id=campaign_id, error=type(error).__name__)
        return
    final_status = "interrupted" if any(s["status"] == "interrupted" for s in read_campaign(campaign_id)["scenes"]) else "completed"
    update_campaign(campaign_id, lambda m: m.update(status=final_status, finished_at=now()))
    make_contact_sheet(campaign_id)
    log_event("campaign_completed", campaign_id=campaign_id)


def review_scene(campaign_id: str, scene_id: str, approved: bool, issues: list[str]) -> dict[str, Any]:
    if not set(issues).issubset(ISSUES):
        raise ValueError("Unknown review issue")
    def save(m: dict[str, Any]) -> None:
        row = next((s for s in m["scenes"] if s["id"] == scene_id), None)
        if row is None or row["status"] != "completed":
            raise ValueError("This scene is not ready to review")
        row.update(review="approved" if approved else "rejected", issues=issues, reviewed_at=now())
    result = update_campaign(campaign_id, save)
    log_event("campaign_scene_reviewed", campaign_id=campaign_id, scene=scene_id, review="approved" if approved else "rejected")
    return result


def campaign_metrics(owner_user_id: str) -> dict[str, Any]:
    campaigns = []
    if ROOT.exists():
        for path in ROOT.glob("*/manifest.json"):
            try:
                campaign = json.loads(path.read_text(encoding="utf-8"))
                if campaign.get("owner_user_id") == owner_user_id:
                    campaigns.append(campaign)
            except (ValueError, OSError):
                pass
    scenes = [scene for campaign in campaigns for scene in campaign["scenes"]]
    completed = [scene for scene in scenes if scene["status"] == "completed"]
    reviewed = [scene for scene in completed if scene["review"] != "pending"]
    approved = [scene for scene in reviewed if scene["review"] == "approved"]
    detail_errors = [scene for scene in reviewed if {"shape", "color", "label"}.intersection(scene["issues"])]
    latencies = [scene["generation_seconds"] for scene in completed if scene["generation_seconds"] is not None]
    previews = [c["first_preview_seconds"] for c in campaigns if c["first_preview_seconds"] is not None]
    reserved = round(sum(c.get("estimated_reserved_usd", 0) for c in campaigns), 3)
    return {
        "campaigns_started": len(campaigns),
        "campaigns_completed": sum(c["status"] == "completed" for c in campaigns),
        "images_generated": len(completed),
        "images_reviewed": len(reviewed),
        "images_approved": len(approved),
        "approval_rate": round(len(approved) / len(reviewed), 3) if reviewed else None,
        "product_detail_error_rate": round(len(detail_errors) / len(reviewed), 3) if reviewed else None,
        "mean_generation_seconds": round(mean(latencies), 2) if latencies else None,
        "mean_time_to_first_preview_seconds": round(mean(previews), 2) if previews else None,
        "estimated_reserved_usd": reserved,
        "estimated_cost_per_approved_usd": round(reserved / len(approved), 3) if approved else None,
        "issue_counts": {issue: sum(issue in s["issues"] for s in reviewed) for issue in sorted(ISSUES)},
        "note": "Your campaigns and one reviewer's decisions; cost figures are model estimates, not ad performance or actual fal billing.",
    }
