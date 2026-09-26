from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet
from PIL import Image

from backend import db as storage
from backend.studio import campaign_dir, read_owned_campaign

GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v26.0")


class SocialError(Exception):
    pass


def configured() -> bool:
    return all(os.getenv(name) for name in (
        "META_APP_ID", "META_APP_SECRET", "META_REDIRECT_URI", "META_TOKEN_ENCRYPTION_KEY", "SOCIAL_PUBLIC_BASE_URL",
    ))


def cipher() -> Fernet:
    try:
        return Fernet(os.environ["META_TOKEN_ENCRYPTION_KEY"].encode())
    except (KeyError, ValueError, TypeError) as error:
        raise SocialError("Social publishing is unavailable in this deployment") from error


def connect() -> sqlite3.Connection:
    db = storage.connect()
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS oauth_states (state TEXT PRIMARY KEY, user_id TEXT NOT NULL, campaign_id TEXT NOT NULL, expires_at INTEGER NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS meta_pages (user_id TEXT NOT NULL, page_id TEXT NOT NULL, name TEXT NOT NULL, ig_id TEXT, token BLOB NOT NULL, PRIMARY KEY (user_id, page_id))")
    db.execute("CREATE TABLE IF NOT EXISTS published_posts (user_id TEXT NOT NULL, campaign_id TEXT NOT NULL, scene_id TEXT NOT NULL, platform TEXT NOT NULL, page_id TEXT NOT NULL, status TEXT NOT NULL, remote_id TEXT, created_at INTEGER NOT NULL, PRIMARY KEY (user_id, campaign_id, scene_id, platform, page_id))")
    db.commit()
    return db


@contextmanager
def database():
    db = connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def graph(path: str, *, token: str | None = None, params: dict[str, str] | None = None, method: str = "GET", image: bytes | None = None) -> dict:
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{path.lstrip('/')}"
    headers = {"User-Agent": "Stillroom/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params)
        data = None
    elif image is not None:
        boundary = secrets.token_hex(16)
        fields = b"".join(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
            for key, value in (params or {}).items()
        )
        data = fields + (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; filename=\"stillroom.jpg\"\r\n"
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode() + image + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    else:
        data = urllib.parse.urlencode(params or {}).encode() if method == "POST" else None
        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as error:
        raise SocialError("Meta did not accept the request. Check the connected account and its permissions.") from error


def start_connection(user_id: str, campaign_id: str) -> str:
    if not configured():
        raise SocialError("Social publishing is unavailable in this deployment")
    read_owned_campaign(campaign_id, user_id)
    state = secrets.token_urlsafe(32)
    with database() as db:
        db.execute("DELETE FROM oauth_states WHERE expires_at < ?", (int(time.time()),))
        db.execute("INSERT INTO oauth_states VALUES (?, ?, ?, ?)", (state, user_id, campaign_id, int(time.time()) + 600))
    params = {
        "client_id": os.environ["META_APP_ID"],
        "redirect_uri": os.environ["META_REDIRECT_URI"],
        "state": state,
        "response_type": "code",
        "scope": "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish",
    }
    return f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth?{urllib.parse.urlencode(params)}"


def finish_connection(code: str, state: str) -> str:
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM oauth_states WHERE state = ?", (state,)).fetchone()
        db.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        if row is None or row["expires_at"] < time.time():
            raise SocialError("This connection request expired. Return to Stillroom and try again.")
        user_id, campaign_id = row["user_id"], row["campaign_id"]
    short = graph("oauth/access_token", params={
        "client_id": os.environ["META_APP_ID"], "client_secret": os.environ["META_APP_SECRET"],
        "redirect_uri": os.environ["META_REDIRECT_URI"], "code": code,
    })["access_token"]
    long_lived = graph("oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": os.environ["META_APP_ID"],
        "client_secret": os.environ["META_APP_SECRET"], "fb_exchange_token": short,
    })["access_token"]
    pages = graph("me/accounts", token=long_lived, params={
        "fields": "id,name,access_token,tasks,instagram_business_account", "limit": "100",
    }).get("data", [])
    if not pages:
        raise SocialError("No Facebook Page was available for this account.")
    encrypt = cipher()
    with database() as db:
        for page in pages:
            if "CREATE_CONTENT" not in page.get("tasks", []):
                continue
            db.execute(
                "INSERT INTO meta_pages VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, page_id) DO UPDATE SET name=excluded.name, ig_id=excluded.ig_id, token=excluded.token",
                (user_id, page["id"], page["name"], (page.get("instagram_business_account") or {}).get("id"),
                 encrypt.encrypt(page["access_token"].encode())),
            )
    return campaign_id


def accounts(user_id: str) -> list[dict]:
    with database() as db:
        rows = db.execute("SELECT page_id, name, ig_id FROM meta_pages WHERE user_id = ? ORDER BY name", (user_id,)).fetchall()
    return [{"page_id": row["page_id"], "name": row["name"], "instagram_available": bool(row["ig_id"])} for row in rows]


def disconnect(user_id: str, page_id: str) -> None:
    with database() as db:
        db.execute("DELETE FROM meta_pages WHERE user_id = ? AND page_id = ?", (user_id, page_id))


def photo_jpeg(path: Path) -> bytes:
    output = io.BytesIO()
    with Image.open(path) as image:
        image.convert("RGB").save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()


def media_signature(campaign_id: str, scene_id: str, expires: int, owner_user_id: str) -> str:
    message = f"{campaign_id}:{scene_id}:{expires}:{owner_user_id}".encode()
    key = os.environ["META_TOKEN_ENCRYPTION_KEY"].encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def public_media(campaign_id: str, scene_id: str, expires: int, signature: str) -> bytes:
    from backend.studio import read_campaign
    if expires < time.time() or expires > time.time() + 3600:
        raise SocialError("This image link expired")
    manifest = read_campaign(campaign_id)
    expected = media_signature(campaign_id, scene_id, expires, manifest["owner_user_id"])
    if not hmac.compare_digest(signature, expected):
        raise SocialError("Invalid image link")
    scene = next((row for row in manifest["scenes"] if row["id"] == scene_id and row["review"] == "approved" and row["file"]), None)
    if scene is None:
        raise SocialError("Image is not approved")
    return photo_jpeg(campaign_dir(campaign_id) / scene["file"])


def posts(user_id: str, campaign_id: str) -> list[dict]:
    with database() as db:
        rows = db.execute("SELECT scene_id, platform, page_id, status, remote_id FROM published_posts WHERE user_id = ? AND campaign_id = ?", (user_id, campaign_id)).fetchall()
    return [dict(row) for row in rows]


def publish(user_id: str, campaign_id: str, scene_id: str, platform: str, page_id: str, caption: str) -> dict:
    if platform not in {"facebook", "instagram"} or not page_id.isdigit():
        raise SocialError("Choose a connected Facebook Page or Instagram account")
    if len(caption) > 2200:
        raise SocialError("Keep the caption under 2,200 characters")
    manifest = read_owned_campaign(campaign_id, user_id)
    scene = next((row for row in manifest["scenes"] if row["id"] == scene_id and row["review"] == "approved" and row["file"]), None)
    if scene is None:
        raise SocialError("Approve the image before publishing")
    with database() as db:
        page = db.execute("SELECT ig_id, token FROM meta_pages WHERE user_id = ? AND page_id = ?", (user_id, page_id)).fetchone()
        if page is None:
            raise SocialError("Connect the destination account first")
        if platform == "instagram" and not page["ig_id"]:
            raise SocialError("This Page has no linked professional Instagram account")
        existing = db.execute("SELECT status, remote_id FROM published_posts WHERE user_id=? AND campaign_id=? AND scene_id=? AND platform=? AND page_id=?",
                              (user_id, campaign_id, scene_id, platform, page_id)).fetchone()
        if existing:
            if existing["status"] == "published":
                return {"status": "published", "remote_id": existing["remote_id"]}
            raise SocialError("A publishing attempt already exists. Check the destination account before trying again.")
        db.execute("INSERT INTO published_posts VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?)",
                   (user_id, campaign_id, scene_id, platform, page_id, int(time.time())))
    try:
        token = cipher().decrypt(page["token"]).decode()
        if platform == "facebook":
            result = graph(f"{page_id}/photos", token=token, method="POST", params={"message": caption, "published": "true"},
                           image=photo_jpeg(campaign_dir(campaign_id) / scene["file"]))
        else:
            if not os.environ["SOCIAL_PUBLIC_BASE_URL"].startswith("https://"):
                raise SocialError("Instagram publishing needs a public HTTPS site")
            expires = int(time.time()) + 3500
            image_url = (os.environ["SOCIAL_PUBLIC_BASE_URL"].rstrip("/") +
                         f"/api/social/media/{campaign_id}/{scene_id}?" + urllib.parse.urlencode({
                             "expires": expires, "signature": media_signature(campaign_id, scene_id, expires, user_id),
                         }))
            container = graph(f"{page['ig_id']}/media", token=token, method="POST", params={"image_url": image_url, "caption": caption})
            for _ in range(10):
                status = graph(container["id"], token=token, params={"fields": "status_code"}).get("status_code")
                if status == "FINISHED":
                    break
                if status in {"ERROR", "EXPIRED"}:
                    raise SocialError("Instagram could not prepare this image")
                time.sleep(3)
            else:
                raise SocialError("Instagram is still preparing the image; check your account before retrying")
            result = graph(f"{page['ig_id']}/media_publish", token=token, method="POST", params={"creation_id": container["id"]})
        remote_id = str(result["id"])
        with database() as db:
            db.execute("UPDATE published_posts SET status='published', remote_id=? WHERE user_id=? AND campaign_id=? AND scene_id=? AND platform=? AND page_id=?",
                       (remote_id, user_id, campaign_id, scene_id, platform, page_id))
        return {"status": "published", "remote_id": remote_id}
    except Exception as error:
        with database() as db:
            db.execute("UPDATE published_posts SET status='needs_check' WHERE user_id=? AND campaign_id=? AND scene_id=? AND platform=? AND page_id=?",
                       (user_id, campaign_id, scene_id, platform, page_id))
        if isinstance(error, SocialError):
            raise
        raise SocialError("Publishing could not be confirmed. Check the destination account.") from error
