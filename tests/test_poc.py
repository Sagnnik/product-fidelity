import io
import json
import os
import tempfile
import time
import unittest
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from cryptography.fernet import Fernet

from backend import db, fal_api, quota, social, studio
from backend.auth import require_user

app_module = import_module("backend.app")


def sample_photo() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (360, 360), "#b83d30").save(buffer, format="PNG")
    return buffer.getvalue()


class PocWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.user = "user_A"
        self.patches = [
            patch.object(db, "DB_PATH", self.root / "db" / "stillroom.sqlite3"),
            patch.object(studio, "ROOT", self.root / "campaigns"),
            patch.object(app_module, "ROOT", self.root / "campaigns"),
            patch.object(fal_api, "DATA_ROOT", self.root),
            patch.object(fal_api, "LOG_FILE", self.root / "LOGS.md"),
            patch.object(fal_api, "LOCK_FILE", self.root / ".fal_call.lock"),
            patch.object(studio, "load_fal_key", return_value=True),
            patch.object(app_module.executor, "submit", return_value=None),
        ]
        for item in self.patches:
            item.start()
        app_module.app.dependency_overrides[require_user] = lambda: self.user
        self.client = TestClient(app_module.app)

    def tearDown(self):
        self.client.close()
        app_module.app.dependency_overrides.clear()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def create(self, byok=False):
        headers = {"X-Fal-Key": "dummy-personal-key"} if byok else {}
        return self.client.post(
            "/api/campaigns",
            data={"product": "red ceramic mug", "audience": "coffee lovers", "critical_details": "unbranded, left handle"},
            files={"image": ("mug.png", sample_photo(), "image/png")},
            headers=headers,
        )

    def test_free_limit_byok_and_ownership(self):
        ids = []
        for _ in range(3):
            response = self.create()
            self.assertEqual(response.status_code, 202)
            ids.append(response.json()["id"])
        self.assertEqual(self.create().status_code, 403)
        self.assertEqual(quota.free_used("user_A"), 3)
        byok = self.create(byok=True)
        self.assertEqual(byok.status_code, 202)
        manifest = byok.json()
        self.assertEqual(manifest["funding"], "byok")
        self.assertIn("unbranded, left handle", manifest["scenes"][0]["prompt"])
        self.assertNotIn("dummy-personal-key", json.dumps(manifest))
        self.assertNotIn("dummy-personal-key", (self.root / "LOGS.md").read_text())
        self.assertEqual(quota.free_used("user_A"), 3)
        self.assertEqual(self.client.get("/api/config").json()["free_campaigns_remaining"], 0)
        self.assertEqual(len(self.client.get("/api/campaigns").json()), 4)

        self.user = "user_B"
        self.assertEqual(self.client.get("/api/campaigns").json(), [])
        self.assertEqual(self.client.get(f"/api/campaigns/{ids[0]}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/campaigns/{ids[0]}/download").status_code, 404)
        self.assertEqual(self.client.get(f"/api/campaigns/{ids[0]}/files/reference.png").status_code, 404)
        self.assertEqual(self.client.get("/api/metrics").json()["campaigns_started"], 0)

    def test_restart_requires_explicit_resume_and_never_repeats_uncertain_image(self):
        campaign_id = self.create().json()["id"]
        def mark_running(item):
            item["status"] = "running"
            item["scenes"][0]["status"] = "running"
        studio.update_campaign(campaign_id, mark_running)
        app_module.executor.submit.reset_mock()

        studio.recover_interrupted_campaigns()
        recovered = studio.read_campaign(campaign_id)
        self.assertEqual(recovered["status"], "interrupted")
        self.assertEqual([scene["status"] for scene in recovered["scenes"]],
                         ["interrupted", "queued", "queued"])
        self.assertEqual(app_module.executor.submit.call_count, 0)

        self.user = "user_B"
        self.assertEqual(self.client.post(f"/api/campaigns/{campaign_id}/resume").status_code, 404)
        self.user = "user_A"
        response = self.client.post(f"/api/campaigns/{campaign_id}/resume")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["scenes"][0]["status"], "interrupted")
        self.assertEqual(app_module.executor.submit.call_count, 1)
        self.assertEqual(self.client.post(f"/api/campaigns/{campaign_id}/resume").status_code, 400)

    def test_completed_image_file_is_recovered_without_new_request(self):
        campaign_id = self.create().json()["id"]
        target = self.root / "campaigns" / campaign_id
        Image.new("RGB", (768, 1024), "#b83d30").save(target / "studio.png")
        studio.update_campaign(campaign_id, lambda item: (item.update(status="running"), item["scenes"][0].update(status="running")))
        app_module.executor.submit.reset_mock()
        studio.recover_interrupted_campaigns()
        recovered = studio.read_campaign(campaign_id)
        self.assertEqual(recovered["scenes"][0]["status"], "completed")
        self.assertEqual(recovered["scenes"][0]["file"], "studio.png")
        self.assertEqual(app_module.executor.submit.call_count, 0)

    def test_exact_ten_megabyte_product_upload(self):
        raw = sample_photo()
        upload = raw + b"\0" * (10 * 1024 * 1024 - len(raw))
        response = self.client.post(
            "/api/campaigns", data={"product": "red ceramic mug", "image_count": "1"},
            files={"image": ("mug.png", upload, "image/png")},
        )
        self.assertEqual(response.status_code, 202)
        campaign_id = response.json()["id"]
        self.assertEqual((self.root / "campaigns" / campaign_id / "source_original.png").stat().st_size, 10 * 1024 * 1024)

    def test_approved_export_excludes_unreviewed_images(self):
        campaign_id = self.create(byok=True).json()["id"]
        target = self.root / "campaigns" / campaign_id
        for scene_id in ("studio", "lifestyle"):
            Image.new("RGB", (768, 1024), "#b83d30").save(target / f"{scene_id}.png")
        def mark_ready(manifest):
            for scene in manifest["scenes"][:2]:
                scene.update(status="completed", file=f"{scene['id']}.png")
        studio.update_campaign(campaign_id, mark_ready)
        self.assertEqual(self.client.get(f"/api/campaigns/{campaign_id}/approved-download").status_code, 409)
        self.assertEqual(self.client.post(f"/api/campaigns/{campaign_id}/reviews/studio", json={"approved": True, "issues": []}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/campaigns/{campaign_id}/reviews/lifestyle", json={"approved": False, "issues": ["label"]}).status_code, 200)
        response = self.client.get(f"/api/campaigns/{campaign_id}/approved-download")
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = archive.namelist()
            self.assertIn("approved/studio.png", names)
            self.assertNotIn("approved/lifestyle.png", names)
            selection = json.loads(archive.read("selection.json"))
            self.assertEqual([row["scene"] for row in selection["selected"]], ["studio"])

    def test_missing_bearer_is_rejected(self):
        app_module.app.dependency_overrides.clear()
        self.assertEqual(self.client.get("/api/campaigns").status_code, 401)

    def test_clerk_session_subject_is_used(self):
        app_module.app.dependency_overrides.clear()
        signed_in = SimpleNamespace(is_signed_in=True, payload={"sub": "user_A"})
        with patch.dict(os.environ, {"CLERK_SECRET_KEY": "dummy-secret", "CLERK_AUTHORIZED_PARTIES": "http://localhost:5173"}):
            with patch("backend.auth.authenticate_request", return_value=signed_in) as verify:
                response = self.client.get("/api/config", headers={"Authorization": "Bearer dummy-token"})
                self.assertEqual(response.status_code, 200)
                options = verify.call_args.args[1]
                self.assertEqual(options.accepts_token, ["session_token"])
                self.assertEqual(options.authorized_parties, ["http://localhost:5173"])
            with patch("backend.auth.authenticate_request", return_value=SimpleNamespace(is_signed_in=False, payload=None)):
                response = self.client.get("/api/config", headers={"Authorization": "Bearer dummy-token"})
                self.assertEqual(response.status_code, 401)

    def test_exhausted_site_budget_does_not_consume_allowance(self):
        with patch.dict(os.environ, {"FAL_MAX_SPEND_USD": "0"}):
            self.assertEqual(self.create().status_code, 403)
            self.assertEqual(quota.free_used("user_A"), 0)

    def test_free_allowance_is_atomic_and_invalid_upload_does_not_use_it(self):
        invalid = self.client.post(
            "/api/campaigns",
            data={"product": "red ceramic mug"},
            files={"image": ("bad.png", b"not a photo", "image/png")},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(quota.free_used("user_A"), 0)
        with ThreadPoolExecutor(max_workers=10) as pool:
            accepted = list(pool.map(lambda _: quota.reserve_free_campaign("user_A"), range(10)))
        self.assertEqual(sum(accepted), 3)
        self.assertEqual(quota.free_used("user_A"), 3)

    def test_fal_wrapper_routes_personal_key_without_site_spend(self):
        class FakeClient:
            def __init__(self, key):
                keys.append(key)
            def subscribe(self, endpoint, arguments):
                return {"images": [{"url": "https://example.invalid/image.png"}]}
        keys = []
        with patch.object(fal_api, "site_fal_key", return_value="dummy-site-key"):
            with patch("fal_client.SyncClient", FakeClient):
                fal_api.call("fal-ai/flux-2-pro/edit", {"prompt": "sample"}, width=768, height=1024)
                fal_api.call("fal-ai/flux-2-pro/edit", {"prompt": "sample"}, width=768, height=1024, fal_key="dummy-personal-key")
        self.assertEqual(keys, ["dummy-site-key", "dummy-personal-key"])
        self.assertEqual(float(fal_api.reserved_spend()), 0.06)
        self.assertNotIn("dummy-personal-key", (self.root / "LOGS.md").read_text())

    def test_variable_count_background_and_byok_batches(self):
        response = self.client.post(
            "/api/campaigns",
            data={"product": "black headphones", "image_count": "10", "scene_description": "a quiet blue gallery"},
            files={"image": ("product.png", sample_photo(), "image/png"),
                   "background": ("room.png", sample_photo(), "image/png")},
        )
        self.assertEqual(response.status_code, 202)
        manifest = response.json()
        self.assertEqual(len(manifest["scenes"]), 10)
        self.assertIn("image 2", manifest["scenes"][0]["prompt"])
        self.assertIn("quiet blue gallery", manifest["scenes"][0]["prompt"])
        self.assertTrue((self.root / "campaigns" / manifest["id"] / "background.png").is_file())
        self.assertEqual(self.client.get(f"/api/campaigns/{manifest['id']}/files/background.png").status_code, 200)
        over = self.client.post("/api/campaigns", data={"product": "black headphones", "image_count": "11"},
                                files={"image": ("product.png", sample_photo(), "image/png")})
        self.assertEqual(over.status_code, 400)
        self.assertEqual(quota.free_used(self.user), 1)

        byok = self.create(byok=True).json()
        studio.update_campaign(byok["id"], lambda item: item.update(status="completed"))
        for _ in range(3):
            more = self.client.post(f"/api/campaigns/{byok['id']}/images", data={"image_count": "10"},
                                    headers={"X-Fal-Key": "dummy-personal-key"})
            self.assertEqual(more.status_code, 202)
            studio.update_campaign(byok["id"], lambda item: item.update(status="completed"))
        self.assertEqual(len(studio.read_campaign(byok["id"])["scenes"]), 33)
        self.assertEqual(self.client.post(f"/api/campaigns/{manifest['id']}/images", data={"image_count": "1"},
                                          headers={"X-Fal-Key": "dummy-personal-key"}).status_code, 400)
        self.assertNotIn("dummy-personal-key", (self.root / "campaigns" / byok["id"] / "manifest.json").read_text())

    def test_free_campaign_can_fill_remaining_slots_without_extra_allowance(self):
        response = self.client.post("/api/campaigns", data={"product": "black headphones", "image_count": "2"},
                                    files={"image": ("product.png", sample_photo(), "image/png")})
        self.assertEqual(response.status_code, 202)
        campaign_id = response.json()["id"]
        studio.update_campaign(campaign_id, lambda item: item.update(status="completed", estimated_reserved_usd=0.12))
        more = self.client.post(f"/api/campaigns/{campaign_id}/images", data={"image_count": "8"})
        self.assertEqual(more.status_code, 202)
        self.assertEqual(len(more.json()["scenes"]), 10)
        self.assertEqual(quota.free_used(self.user), 1)
        studio.update_campaign(campaign_id, lambda item: item.update(status="completed"))
        self.assertEqual(self.client.post(f"/api/campaigns/{campaign_id}/images", data={"image_count": "1"}).status_code, 400)
        self.assertEqual(self.client.post(f"/api/campaigns/{campaign_id}/images", data={"image_count": "1"},
                                          headers={"X-Fal-Key": "dummy-personal-key"}).status_code, 400)

    def test_repeated_scenes_get_distinct_seeds(self):
        response = self.client.post(
            "/api/campaigns",
            data={"product": "red ceramic mug", "image_count": "5",
                  "scene_description": "a warm cream studio sweep"},
            files={"image": ("mug.png", sample_photo(), "image/png")},
            headers={"X-Fal-Key": "dummy-personal-key"},
        )
        self.assertEqual(response.status_code, 202)
        campaign_id = response.json()["id"]
        seeds = []
        class FakeClient:
            def __init__(self, key):
                self.key = key
            def upload_file(self, path):
                return "https://example.invalid/reference.png"
            def subscribe(self, endpoint, arguments):
                seeds.append(arguments["seed"])
                return {"images": [{"url": "https://example.invalid/image.png"}], "seed": arguments["seed"]}
        def fake_download(url, destination):
            Image.new("RGB", (768, 1024), "#b83d30").save(destination, format="PNG")
        with patch("fal_client.SyncClient", FakeClient):
            with patch.object(studio, "download_image", side_effect=fake_download):
                studio.generate_campaign(campaign_id, fal_key="dummy-personal-key")
        manifest = studio.read_campaign(campaign_id)
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(seeds, [studio.SEED + index for index in range(5)])
        self.assertEqual([scene["seed"] for scene in manifest["scenes"]], seeds)
        self.assertTrue(all(scene["file"] for scene in manifest["scenes"]))

    def test_meta_connection_approved_only_publish_and_signed_media(self):
        campaign = self.create(byok=True).json()
        campaign_id = campaign["id"]
        target = self.root / "campaigns" / campaign_id
        Image.new("RGB", (768, 1024), "#b83d30").save(target / "studio.png")
        def mark_ready(item):
            item["scenes"][0].update(status="completed", file="studio.png", review="approved")
        studio.update_campaign(campaign_id, mark_ready)
        graph_calls = []
        def fake_graph(path, **kwargs):
            graph_calls.append((path, kwargs))
            if path == "oauth/access_token":
                return {"access_token": "dummy-meta-token"}
            if path == "me/accounts":
                return {"data": [{"id": "123", "name": "Test Page", "access_token": "dummy-page-token",
                                  "tasks": ["CREATE_CONTENT"], "instagram_business_account": {"id": "456"}}]}
            if path == "123/photos":
                return {"id": "789"}
            if path == "456/media":
                return {"id": "container123"}
            if path == "container123":
                return {"status_code": "FINISHED"}
            if path == "456/media_publish":
                return {"id": "ig789"}
            raise AssertionError(path)
        settings = {
            "META_APP_ID": "dummy-app", "META_APP_SECRET": "dummy-secret",
            "META_REDIRECT_URI": "https://example.test/api/social/callback",
            "META_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "SOCIAL_PUBLIC_BASE_URL": "https://example.test",
        }
        with patch.dict(os.environ, settings), patch.object(social, "graph", side_effect=fake_graph):
            self.assertEqual(self.client.get("/api/social/config").json()["accounts"], [])
            connect = self.client.post("/api/social/connect", json={"campaign_id": campaign_id})
            self.assertEqual(connect.status_code, 200)
            state = urllib.parse.parse_qs(urllib.parse.urlparse(connect.json()["url"]).query)["state"][0]
            callback = self.client.get("/api/social/callback", params={"code": "dummy-code", "state": state}, follow_redirects=False)
            self.assertEqual(callback.status_code, 303)
            self.assertEqual(len(self.client.get("/api/social/config").json()["accounts"]), 1)
            self.assertNotIn("dummy-page-token", (self.root / "db" / "stillroom.sqlite3").read_bytes().decode(errors="ignore"))
            expiry = int(time.time()) + 300
            signature = social.media_signature(campaign_id, "studio", expiry, self.user)
            media = self.client.get(f"/api/social/media/{campaign_id}/studio", params={"expires": expiry, "signature": signature})
            self.assertEqual(media.status_code, 200)
            self.assertEqual(media.headers["content-type"], "image/jpeg")
            self.assertEqual(self.client.get(f"/api/social/media/{campaign_id}/studio", params={"expires": expiry, "signature": "wrong"}).status_code, 404)
            bad = self.client.post(f"/api/campaigns/{campaign_id}/publish", json={"scene_id": "lifestyle", "platform": "facebook", "page_id": "123"})
            self.assertEqual(bad.status_code, 400)
            published = self.client.post(f"/api/campaigns/{campaign_id}/publish", json={"scene_id": "studio", "platform": "facebook", "page_id": "123", "caption": "Hello"})
            self.assertEqual(published.json()["remote_id"], "789")
            self.assertEqual(self.client.post(f"/api/campaigns/{campaign_id}/publish", json={"scene_id": "studio", "platform": "facebook", "page_id": "123"}).json()["remote_id"], "789")
            self.assertEqual(sum(path == "123/photos" for path, _ in graph_calls), 1)
            instagram = self.client.post(f"/api/campaigns/{campaign_id}/publish", json={"scene_id": "studio", "platform": "instagram", "page_id": "123", "caption": "Hello"})
            self.assertEqual(instagram.json()["remote_id"], "ig789")
            self.assertEqual(len(self.client.get(f"/api/social/posts/{campaign_id}").json()), 2)
            self.user = "user_B"
            self.assertEqual(self.client.post(f"/api/campaigns/{campaign_id}/publish", json={"scene_id": "studio", "platform": "facebook", "page_id": "123"}).status_code, 404)
            self.user = "user_A"
            self.assertEqual(self.client.delete("/api/social/accounts/123").status_code, 200)


if __name__ == "__main__":
    unittest.main()
