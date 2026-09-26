# Stillroom

**Product photos in. Reviewable campaign concepts out.**

Stillroom turns a product photo and short campaign brief into portrait ad-photo concepts. Each image stays connected to its source, prompt, and review decision so a marketer can compare details, flag defects, and export a clean set of approved images.

The application uses [FLUX.2 Pro edit](https://fal.ai/models/fal-ai/flux-2-pro/edit) for reference-guided generation, FastAPI for the API, and React with Tailwind CSS for the studio. Clerk handles sign-in. Image quality still depends on the source and model output, so review is part of the workflow before export.

## What you can do

- **Generate a campaign:** Open `/create`, upload a product photo, and choose 1–10 portrait images. Explore the studio, lifestyle, and celebration rotation, describe your own setting, or use a background photo as a second reference. Add a scene description alongside the background when you want more direction.
- **Review against the source:** Compare each result beside the original. Mark it usable or tag issues such as changed shape or color, invented labels, lighting problems, visual artifacts, poor scene fit, or extra products.
- **Export a selection:** Download approved images with the original source and a `selection.json` file containing the brief, prompts, model, and seed. A separate internal archive preserves every draft and its review history.
- **Control access and spend:** Clerk scopes campaigns and files to their owner. Each account has a limited project-funded allowance, with an option to use a personal fal key. Project-funded requests use a configurable spend cap and run one at a time.
- **Browse campaign history:** Reopen campaigns in an image-led gallery. Optional workflow metrics are tucked into a disclosure below the images.
- **Publish an approved image:** Connect a Facebook Page through Meta, choose the Page or its linked professional Instagram account, write a caption, and publish only after explicitly selecting an approved image. This optional feature requires Meta app configuration and platform permissions.

## Quick start

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 20+, a [Clerk application](https://clerk.com/docs/react/getting-started/quickstart), and a [fal API key](https://fal.ai/dashboard/keys).

```bash
uv sync
npm ci --prefix frontend
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

Set these values in the copied files:

| File | Variable | Purpose |
| --- | --- | --- |
| `.env` | `FAL_API_KEY` | Server key for project-funded image generation. |
| `.env` | `CLERK_SECRET_KEY` | Server key for Clerk session verification. |
| `.env` | `CLERK_AUTHORIZED_PARTIES` | Comma-separated frontend origins allowed in Clerk session tokens, such as `http://127.0.0.1:5173`. |
| `frontend/.env.local` | `VITE_CLERK_PUBLISHABLE_KEY` | Public Clerk key included in the frontend build. |

Optional server settings are `FAL_MAX_SPEND_USD` (default `8.00`), `STILLROOM_DATA_DIR` (persistent file storage), and `CLERK_JWT_KEY` (local JWT verification). Keep secret keys in ignored local files or deployment variables.

Start the API and frontend in separate terminals:

```bash
uv run uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

```bash
npm run dev --prefix frontend -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`, then use `/create` to prepare a campaign. Vite forwards `/api` requests to FastAPI. You can prepare a brief before signing in; Stillroom prompts for sign-in or sign-up when you try to generate. Image generation starts only after an authenticated submission.

## Campaigns, review, and storage

A campaign starts with 1–10 portrait drafts; three is the default. With no scene input, the studio rotates through three suggested settings. A custom scene description replaces those suggestions. An uploaded background becomes a second model reference and is saved with the source. When the background photo is the only scene input, its setting is used in place of the presets. The model may reinterpret a background and may change product details, so each result still needs review. The server saves the source photos, prepared references, brief, prompts, model ID, seed, generated images, timings, review labels, and a contact sheet of the first 20 results. Reviewers can revisit a campaign and change their decisions. The approved export is available once at least one image is marked usable.

The `/history` page shows your saved campaign images first. Expand **View workflow metrics** to see generation time, time to first preview, review decisions, issue rates, and estimated spend per approved image. These are workflow measures from your own reviews, not ad-performance scores.

Each Clerk user has an allowance of up to three project-funded campaigns, with up to ten images in each, subject to the project spend cap. A campaign uses one allowance when it is accepted for generation; the owner may fill unused image slots later without consuming another allowance. BYOK campaigns have no app-set total image count: the owner can add further batches of 1–10 images using their own fal key. The personal key is held in browser and worker memory for each request rather than stored with results. Project-funded calls are serialized through `backend/fal_api.py`, which records a conservative cost reservation before each request, including failed requests. Reservations are budget controls, not actual fal billing; check the [fal usage dashboard](https://fal.ai/dashboard/usage) for charges.

## Optional Meta publishing

Set `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI`, `META_TOKEN_ENCRYPTION_KEY`, and `SOCIAL_PUBLIC_BASE_URL` in the server environment. `META_REDIRECT_URI` must exactly match the HTTPS callback registered in your Meta app, ending in `/api/social/callback`. `SOCIAL_PUBLIC_BASE_URL` is the public HTTPS origin serving this FastAPI app. Generate one Fernet key with the command in `.env.example` and retain it across deployments; replacing it disconnects saved accounts. The Page access tokens are encrypted in the ignored `db/stillroom.sqlite3` database.

Request the `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`, and `instagram_content_publish` permissions in Meta. Instagram publishing here uses a professional account linked to a Facebook Page; a personal Instagram account is not an eligible destination. Meta may require app review before people outside your app's test roles can connect. The app serves an approved image through a one-hour signed HTTPS URL so Instagram can retrieve it. A publish attempt is recorded before contacting Meta to avoid accidental duplicate posts; if its outcome cannot be confirmed, check the destination account before attempting further posting.

See Meta's [official Instagram API collection](https://www.postman.com/meta/instagram/collection/6yqw8pt/instagram-api) for account and permission setup.

Stillroom stores campaign files under `outputs/campaigns/`, free-use counts and optional encrypted Meta connections in `db/stillroom.sqlite3`, and spend reservations in `LOGS.md`, all beneath the configured data directory. These local artifacts and credentials are ignored by Git.

## Project layout

| Path | Responsibility |
| --- | --- |
| `backend/app.py` | FastAPI routes, ownership checks, and exports. |
| `backend/studio.py` | Reference preparation, scene prompts, generation, and reviews. |
| `backend/fal_api.py` | Serialized fal calls and spend reservations. |
| `backend/auth.py`, `backend/quota.py` | Clerk session verification and free-use accounting. |
| `backend/social.py` | Optional Meta OAuth connection, signed media access, and explicit publishing. |
| `frontend/src/` | React studio and authenticated API client. |
| `tests/` | No-charge workflow and access-control checks. |

## Deployment

Deploy the repository root as **one Railway service**. The root Dockerfile builds the React frontend and serves it through FastAPI alongside the API. Set `VITE_CLERK_PUBLISHABLE_KEY` as a Railway service variable before building; Vite embeds this public key in the frontend bundle. The Docker build stops if it is missing.

The frontend currently calls relative `/api` URLs, so this is a single-origin deployment. A separate Vercel frontend needs API routing and origin configuration before it will work.

For a manual deployment, build the frontend and run one API worker:

```bash
npm run build --prefix frontend
uv run uvicorn backend.app:app --host 0.0.0.0 --port "$PORT"
```

Set `FAL_API_KEY`, `CLERK_SECRET_KEY`, `CLERK_AUTHORIZED_PARTIES` (the exact Railway public origin), and `FAL_MAX_SPEND_USD` as server variables. Attach a writable Railway volume for campaigns, the spend log, and `db/stillroom.sqlite3`; the app uses `RAILWAY_VOLUME_MOUNT_PATH` automatically. Set the Railway healthcheck path to `/api/health` and keep the service at one replica.

Leave Railway Serverless mode **off** for this version. Generation runs in an in-process queue after the API returns, and the queue does not recover jobs after a container stops. A restart or sleep during a campaign can leave it unfinished. Configure Clerk sign-up access and the project spend cap before enabling project-funded generation on a public domain. Optional Meta publishing can stay unconfigured; the UI treats it as coming later.

For a public launch, use a Clerk production instance and a stable domain. Clerk development keys are suitable for a restricted staging demo, but Clerk does not recommend development instances for production traffic.

## Development checks

```bash
uv run python -m unittest discover -s tests -v
npm run build --prefix frontend
```

The tests use fake fal clients and a temporary database; they do not submit paid image requests.
