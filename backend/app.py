from __future__ import annotations

import io
import json
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.auth import UserId
from backend.fal_api import estimated_cost, load_fal_key, reserved_spend
from backend.quota import FREE_CAMPAIGNS, free_used, release_free_campaign, reserve_free_campaign
from backend import social
from backend.studio import (
    ENDPOINT, HEIGHT, ISSUES, MAX_BATCH_IMAGES, MAX_UPLOAD_BYTES, ROOT, SCENES, WIDTH,
    add_images, campaign_dir, campaign_metrics, generate_campaign, read_owned_campaign,
    recover_interrupted_campaigns, resume_queued_campaign, review_scene, start_campaign,
)

app = FastAPI(title="Frame / Ad Photo Studio", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Fal-Key"],
)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="campaign")


@app.on_event("startup")
def reconcile_campaigns() -> None:
    recover_interrupted_campaigns()


class ReviewRequest(BaseModel):
    approved: bool
    issues: list[str] = []


class SocialConnectRequest(BaseModel):
    campaign_id: str


class PublishRequest(BaseModel):
    scene_id: str
    platform: str
    page_id: str
    caption: str = ""


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config(user_id: UserId) -> dict:
    per_image = estimated_cost(ENDPOINT, WIDTH, HEIGHT)
    free_budget_available = reserved_spend() + per_image <= Decimal(os.getenv("FAL_MAX_SPEND_USD", "8.00"))
    return {
        "model": ENDPOINT,
        "size": [WIDTH, HEIGHT],
        "scenes": SCENES,
        "issues": sorted(ISSUES),
        "key_present": load_fal_key(),
        "estimated_max_per_image_usd": float(per_image),
        "estimated_max_campaign_usd": float(per_image * len(SCENES)),
        "max_free_images_per_campaign": MAX_BATCH_IMAGES,
        "reserved_spend_usd": float(reserved_spend()),
        "spend_limit_usd": float(os.getenv("FAL_MAX_SPEND_USD", "8.00")),
        "free_campaigns_remaining": max(0, FREE_CAMPAIGNS - free_used(user_id)),
        "free_campaigns_total": FREE_CAMPAIGNS,
        "free_budget_available": free_budget_available,
    }


@app.get("/api/campaigns")
def list_campaigns(user_id: UserId) -> list[dict]:
    if not ROOT.exists():
        return []
    campaigns = []
    for path in ROOT.glob("*/manifest.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("owner_user_id") != user_id:
                continue
            ready = [scene for scene in item["scenes"] if scene["status"] == "completed" and scene["file"]]
            preview = next((scene for scene in ready if scene["review"] == "approved"), None)
            if preview is None:
                preview = ready[0] if ready else None
            campaigns.append({
                "id": item["id"], "status": item["status"], "created_at": item["created_at"],
                "product": item["product"],
                "images_generated": len(ready),
                "preview_file": preview["file"] if preview else None,
            })
        except (OSError, ValueError, KeyError):
            continue
    return sorted(campaigns, key=lambda item: item["created_at"], reverse=True)


@app.post("/api/campaigns", status_code=202)
async def create_campaign(
    user_id: UserId,
    image: UploadFile = File(...),
    product: str = Form(...),
    audience: str = Form(""),
    critical_details: str = Form(""),
    scene_description: str = Form(""),
    image_count: int = Form(3),
    background: UploadFile | None = File(default=None),
    x_fal_key: str | None = Header(default=None),
) -> dict:
    raw = await image.read(MAX_UPLOAD_BYTES + 1)
    await image.close()
    background_raw = await background.read(MAX_UPLOAD_BYTES + 1) if background is not None else None
    if background is not None:
        await background.close()
    fal_key = x_fal_key.strip() if x_fal_key else None
    if fal_key and len(fal_key) > 500:
        raise HTTPException(status_code=400, detail="fal key is too long")
    if not 1 <= image_count <= MAX_BATCH_IMAGES:
        raise HTTPException(status_code=400, detail="Choose between 1 and 10 images per batch")
    per_image = estimated_cost(ENDPOINT, WIDTH, HEIGHT, input_images=2 if background_raw is not None else 1)
    if fal_key is None and reserved_spend() + per_image * image_count > Decimal(os.getenv("FAL_MAX_SPEND_USD", "8.00")):
        raise HTTPException(status_code=403, detail="The studio's free budget is exhausted. Use your own fal key to continue.")
    if fal_key is None and not reserve_free_campaign(user_id):
        raise HTTPException(status_code=403, detail="Three free campaigns used. Add your own fal key to continue.")
    try:
        manifest = start_campaign(
            raw, product, audience, critical_details,
            owner_user_id=user_id, funding="byok" if fal_key else "free",
            image_count=image_count, scene_description=scene_description, background_raw=background_raw,
        )
    except ValueError as error:
        if fal_key is None:
            release_free_campaign(user_id)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception:
        if fal_key is None:
            release_free_campaign(user_id)
        raise
    executor.submit(generate_campaign, manifest["id"], fal_key)
    return manifest


@app.post("/api/campaigns/{campaign_id}/images", status_code=202)
def create_more_images(
    campaign_id: str, user_id: UserId, image_count: int = Form(3), x_fal_key: str | None = Header(default=None),
) -> dict:
    fal_key = x_fal_key.strip() if x_fal_key else None
    if fal_key and len(fal_key) > 500:
        raise HTTPException(status_code=400, detail="fal key is too long")
    if not 1 <= image_count <= MAX_BATCH_IMAGES:
        raise HTTPException(status_code=400, detail="Choose between 1 and 10 images per batch")
    try:
        current = read_owned_campaign(campaign_id, user_id)
        if current["funding"] == "byok" and not fal_key:
            raise ValueError("Enter your fal key to add images")
        if current["funding"] == "free" and fal_key:
            raise ValueError("This campaign uses project credit; start a BYOK campaign for unlimited images")
        per_image = estimated_cost(ENDPOINT, WIDTH, HEIGHT, input_images=2 if current.get("background_file") else 1)
        if fal_key is None and reserved_spend() + per_image * image_count > Decimal(os.getenv("FAL_MAX_SPEND_USD", "8.00")):
            raise HTTPException(status_code=403, detail="The studio's free budget is exhausted. Use your own fal key to continue.")
        manifest = add_images(campaign_id, image_count)
    except ValueError as error:
        raise HTTPException(status_code=404 if str(error) == "Unknown campaign" else 400, detail=str(error)) from error
    executor.submit(generate_campaign, campaign_id, fal_key)
    return manifest


@app.post("/api/campaigns/{campaign_id}/resume", status_code=202)
def resume_campaign(
    campaign_id: str, user_id: UserId, x_fal_key: str | None = Header(default=None),
) -> dict:
    fal_key = x_fal_key.strip() if x_fal_key else None
    if fal_key and len(fal_key) > 500:
        raise HTTPException(status_code=400, detail="fal key is too long")
    try:
        current = read_owned_campaign(campaign_id, user_id)
        if current["funding"] == "byok" and not fal_key:
            raise ValueError("Enter your fal key to continue")
        if current["funding"] == "free" and fal_key:
            raise ValueError("This campaign uses project credit")
        manifest = resume_queued_campaign(campaign_id)
    except ValueError as error:
        raise HTTPException(status_code=404 if str(error) == "Unknown campaign" else 400, detail=str(error)) from error
    executor.submit(generate_campaign, campaign_id, fal_key)
    return manifest


@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, user_id: UserId) -> dict:
    try:
        return read_owned_campaign(campaign_id, user_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/campaigns/{campaign_id}/files/{filename}")
def campaign_file(campaign_id: str, filename: str, user_id: UserId) -> FileResponse:
    try:
        manifest = read_owned_campaign(campaign_id, user_id)
        allowed = {manifest["source_file"], manifest["reference_file"], "contact_sheet.jpg"}
        if manifest.get("background_file"):
            allowed.add(manifest["background_file"])
        allowed.update(scene["file"] for scene in manifest["scenes"] if scene["file"])
        path = campaign_dir(campaign_id) / filename
        if filename not in allowed or not path.is_file():
            raise ValueError("Unknown file")
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return FileResponse(path)


@app.post("/api/campaigns/{campaign_id}/reviews/{scene_id}")
def save_review(campaign_id: str, scene_id: str, review: ReviewRequest, user_id: UserId) -> dict:
    try:
        read_owned_campaign(campaign_id, user_id)
        return review_scene(campaign_id, scene_id, review.approved, review.issues)
    except ValueError as error:
        raise HTTPException(status_code=404 if str(error) == "Unknown campaign" else 400, detail=str(error)) from error


@app.get("/api/campaigns/{campaign_id}/download")
def download_campaign(campaign_id: str, user_id: UserId) -> StreamingResponse:
    try:
        manifest = read_owned_campaign(campaign_id, user_id)
        target = campaign_dir(campaign_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    files = ["manifest.json", manifest["source_file"], manifest["reference_file"], "contact_sheet.jpg"]
    if manifest.get("background_file"):
        files.append(manifest["background_file"])
    files.extend(scene["file"] for scene in manifest["scenes"] if scene["file"])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in files:
            path = target / filename
            if path.is_file():
                archive.write(path, arcname=filename)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="campaign-{campaign_id}.zip"'
    })


@app.get("/api/campaigns/{campaign_id}/approved-download")
def download_approved(campaign_id: str, user_id: UserId) -> StreamingResponse:
    try:
        manifest = read_owned_campaign(campaign_id, user_id)
        target = campaign_dir(campaign_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    selected = [scene for scene in manifest["scenes"] if scene["review"] == "approved" and scene["file"]]
    if not selected:
        raise HTTPException(status_code=409, detail="Approve at least one image before export")
    summary = {
        "campaign_id": campaign_id,
        "product": manifest["product"],
        "audience": manifest["audience"],
        "critical_details": manifest.get("critical_details", ""),
        "scene_description": manifest.get("scene_description", ""),
        "model_id": manifest["model_id"],
        "seed": manifest["seed"],
        "size": manifest["size"],
        "selected": [
            {"scene": scene["id"], "name": scene["name"], "prompt": scene["prompt"], "file": scene["file"]}
            for scene in selected
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("selection.json", json.dumps(summary, indent=2) + "\n")
        archive.write(target / manifest["source_file"], arcname=manifest["source_file"])
        for scene in selected:
            archive.write(target / scene["file"], arcname=f"approved/{scene['file']}")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="approved-{campaign_id}.zip"'
    })


@app.get("/api/metrics")
def metrics(user_id: UserId) -> dict:
    return campaign_metrics(user_id)


@app.get("/api/social/config")
def social_config(user_id: UserId) -> dict:
    return {"enabled": social.configured(), "accounts": social.accounts(user_id)}


@app.post("/api/social/connect")
def social_connect(request: SocialConnectRequest, user_id: UserId) -> dict:
    try:
        return {"url": social.start_connection(user_id, request.campaign_id)}
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except social.SocialError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/social/callback", include_in_schema=False)
def social_callback(code: str = "", state: str = "") -> Response:
    try:
        campaign_id = social.finish_connection(code, state)
    except (social.SocialError, KeyError):
        return HTMLResponse("Meta connection failed. Return to Stillroom and try again.", status_code=400)
    return RedirectResponse(f"/create?run={campaign_id}&social=connected#campaign-results", status_code=303)


@app.delete("/api/social/accounts/{page_id}")
def social_disconnect(page_id: str, user_id: UserId) -> dict:
    social.disconnect(user_id, page_id)
    return {"status": "disconnected"}


@app.get("/api/social/posts/{campaign_id}")
def social_posts(campaign_id: str, user_id: UserId) -> list[dict]:
    try:
        read_owned_campaign(campaign_id, user_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return social.posts(user_id, campaign_id)


@app.get("/api/social/media/{campaign_id}/{scene_id}", include_in_schema=False)
def social_media(campaign_id: str, scene_id: str, expires: int, signature: str) -> Response:
    try:
        image = social.public_media(campaign_id, scene_id, expires, signature)
    except (social.SocialError, ValueError, KeyError):
        raise HTTPException(status_code=404, detail="Image link unavailable") from None
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60", "X-Robots-Tag": "noindex"})


@app.post("/api/campaigns/{campaign_id}/publish")
def publish_scene(campaign_id: str, request: PublishRequest, user_id: UserId) -> dict:
    if not social.configured():
        raise HTTPException(status_code=503, detail="Social publishing is unavailable in this deployment")
    try:
        return social.publish(user_id, campaign_id, request.scene_id, request.platform, request.page_id, request.caption)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except social.SocialError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if dist.is_dir():
    @app.get("/create", include_in_schema=False)
    @app.get("/create/", include_in_schema=False)
    def create_page() -> FileResponse:
        return FileResponse(dist / "index.html")

    @app.get("/history", include_in_schema=False)
    @app.get("/history/", include_in_schema=False)
    def history_page() -> FileResponse:
        return FileResponse(dist / "index.html")

    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
