# Project brief for coding agents

Build a small product-preserving ad creative experiment for a Glance India resume application. The repo currently contains setup and a fal client wrapper. Generation, segmentation, and evaluation are still to be implemented.

Keep the implementation MVP-sized. Keep only code and files that the working experiment needs. Remove unused helpers and dependencies as the project takes shape. Prefer straightforward code over defensive frameworks.

Treat 1 GB as the available VPS storage budget for this project. Use fal for generation and avoid downloading large model weights to the Railway volume. Check disk use before adding evaluation dependencies.

Keep the experiment small enough to finish in a day: four opaque product images, three scene prompts, one seed, and three methods per case. The methods are text-only FLUX.1 dev, image-to-image FLUX.1 dev, and a background generated with FLUX.1 dev plus an exact product cutout placed at a fixed location. Keep the original product pixels unchanged in its opaque interior.

All billable fal calls must go through `product_fidelity.fal_api.call`, one request at a time. Check endpoint prices before changing the model list. The default `FAL_MAX_SPEND_USD` is 8. The ignored `LOGS.md` records estimated spend before each request, including failed requests. Do not run paid calls merely to check that setup works. Never print, commit, or paste `FAL_API_KEY` or `FAL_KEY` into a conversation.

Use `LOGS.md` as the human-readable project journal. Record each implementation step, why it was chosen, failures, fixes, visual findings, measured results, and what the numbers do and do not establish. Explain enough that the user can discuss the work in an interview. Keep it ignored by Git.

This project has a 24-hour deadline. Check the first matched comparison before scaling to the batch. If the output is not credible as a product ad, the comparison cannot be measured honestly, or another issue makes the project unlikely to yield a defensible resume result in time, tell the user immediately and recommend using an existing project instead. Do not wait for the full batch to fail.

Save source images, prompts, masks, seeds, model IDs, generated outputs, and a comparison grid. Evaluate product-crop DINOv2 cosine similarity and CLIP image-text similarity, and record visible cutout or lighting defects. A direct composite is expected to win identity similarity; do not present that alone as proof of better ad quality. Count missing products in the text-only baseline. Do not put unmeasured numbers on the resume.

Keep local secrets, source images, generated images, logs, and other nonessential artifacts out of Git. Add such paths to `.gitignore`. Before making the repository public, remove this `AGENTS.md` from the published version and check the public history as well; deleting a tracked file from the current tree does not remove it from earlier commits.
