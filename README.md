# Product fidelity in generated ad creatives

Small experiment: can a generated commercial scene keep the original product intact without losing scene alignment?

## Setup

This project uses fal for image generation, so the VPS does not need a GPU. Install dependencies with `uv sync`, then run `uv run product-fidelity doctor` and `uv run product-fidelity plan`. The commands make no paid API calls.

Create a fal API key at [fal's key dashboard](https://fal.ai/dashboard/keys). In a terminal on the machine where you will run the experiment, execute `uv run product-fidelity configure-key` and paste the key at the hidden prompt. This writes an untracked `.env` file with owner-only permissions. Never paste the key into a T3 chat, commit it, or put it in a GitHub issue. The generation client reads `FAL_KEY` from the environment or `.env`.

The local spending guard starts at **$8** and records estimated charges in `.usage/fal-ledger.json` before each call. It applies only to calls made through `product_fidelity.fal_api.call`. It is a safeguard, not fal account billing. Check the [fal usage dashboard](https://fal.ai/dashboard/usage) as well. fal charges prepaid credits for API use; keep auto top-up off if you want the account balance to be the upper limit.

## Experiment

Use four opaque product photos and three scene prompts at 768 x 1024. For each pair, compare:

1. Text only: `fal-ai/flux-1/dev`
2. Reference image: `fal-ai/flux-1/dev/image-to-image`
3. Preserved product: generate a background with FLUX.1 dev, then place the original segmented product at a fixed position. Optional background-only inpainting can use `fal-ai/flux-pro/v1/fill`.

Save prompts, seeds, inputs, masks, model IDs, and outputs. Compare DINOv2 similarity on the product crop, CLIP text-image similarity for scene alignment, and visible compositing defects. Directly copying the product almost guarantees higher identity similarity, so the visual defect review matters. A text-only output that omits the product should be counted as a missing-product case.

At the [listed prices on 2026-09-25](https://fal.ai/models/fal-ai/flux-1/dev), two FLUX.1 dev calls and one FLUX.1 dev image-to-image call per case cost about $0.075 for a one-megapixel output, or about $0.90 for 12 cases. If preserved generation instead uses FLUX.1 pro Fill, the three-call estimate is about $1.20. Pricing and output sizes can change; run the planner and check model pages before generating.

Inputs, outputs, local secrets, and usage records stay out of Git. A later public version can include a small set of permitted example images and aggregate results.

## Remote workspace

The Railway devbox keeps work under `/data/workspaces`. After cloning this repo there, register it with `t3 project add /data/workspaces/product-fidelity` from the VPS terminal. T3 Code stores project registration on the remote server. Run `uv sync` there before beginning work.
