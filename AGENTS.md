# Project brief for coding agents

Build a small product-preserving ad creative experiment for a Glance India resume application. The repo currently contains setup, a fal client wrapper, and a spending guard. Generation, segmentation, and evaluation are still to be implemented.

Keep the experiment small enough to finish in a day: four opaque product images, three scene prompts, one seed, and three methods per case. The methods are text-only FLUX.1 dev, image-to-image FLUX.1 dev, and a background generated with FLUX.1 dev plus an exact product cutout placed at a fixed location. Optional inpainting or edge blending may improve the preserved method, but keep the original product pixels unchanged in its opaque interior.

All billable fal calls must go through `product_fidelity.fal_api.call`. Check endpoint prices before changing the model list. The default `FAL_MAX_SPEND_USD` is 8. The local ledger reserves an estimate before each request, including failed requests. Do not run paid calls merely to check that setup works. Never print, commit, or paste `FAL_KEY` into a conversation.

Save source images, prompts, masks, seeds, model IDs, generated outputs, and a comparison grid. Evaluate product-crop DINOv2 cosine similarity and CLIP image-text similarity, and record visible cutout or lighting defects. A direct composite is expected to win identity similarity; do not present that alone as proof of better ad quality. Count missing products in the text-only baseline. Do not put unmeasured numbers on the resume.

Keep local secrets, source images, generated images, and usage records out of Git unless the user explicitly selects safe example assets to publish.
