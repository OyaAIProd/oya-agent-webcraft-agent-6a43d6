---
name: gemini-image-gen
display_name: "Nano Banana 2 (Gemini Image Generation)"
description: "Generate images with Google's Nano Banana 2 (gemini-3.1-flash-image-preview). Supports text-to-image and image-to-image with native aspect ratio control. Falls back through Nano Banana Pro and Imagen if the preview model is renamed."
category: media
icon: image
skill_type: sandbox
catalog_type: addon
entry_point: scripts/script.py
requirements: "httpx>=0.25"
resource_requirements:
  - env_var: GEMINI_API_KEY
    name: "Google Gemini API Key"
    description: "Get one at https://aistudio.google.com/app/apikey. Platform provides one for catalog skills, but you can override with your own key to skip per-image billing — your Google account will be billed directly."
    required: false
tool_schema:
  name: gemini_image_gen
  description: |
    Generate one or more images. Routes through Imagen (text-to-image, native
    aspect ratio control) by default, or Gemini Flash Image (image-to-image)
    when reference_image_b64 is provided for visual coherence across a series.
    Returns sandbox file paths plus signed URLs (the platform auto-builds URLs
    via the A2ABASEAI_FILE marker pattern). Pass the URLs to instagram_publish.
    No raw image bytes are returned — that would blow past the LLM context window
    (a single 1MB PNG = ~1.5M base64 chars).
  parameters:
    type: object
    properties:
      prompt:
        type: "string"
        description: "What to draw. Be specific: subject, style, lighting, composition. The more visual detail, the better."
      reference_image_b64:
        type: "string"
        description: "Optional. Base64-encoded reference image for image-to-image generation. Routes through Gemini Flash Image instead of Imagen. Only use when you actually have a reference image — passing it disables aspect_ratio control (Gemini Flash Image always returns squares)."
      num_images:
        type: "integer"
        description: "How many images to generate (1–4). Default 1."
      aspect_ratio:
        type: "string"
        description: "Aspect ratio for text-to-image (Imagen path): '1:1', '9:16' (portrait/Reel cover), '16:9', '4:5' (IG feed), '3:4', '4:3'. Ignored for image-to-image (Gemini Flash Image returns 1024x1024). Default '1:1'."
    required: [prompt]
---
# Nano Banana 2 — Image Generation

Calls Google's **Nano Banana 2** (`gemini-3.1-flash-image-preview`) — the
current generation of Gemini's image model that powers viral AI memes,
poster art, and social-media creative. Use it to make scroll-stopping visuals
on demand: product shots, abstract concept art, founder portraits, meme images,
hero banners, anything you can describe in words.

## When this is the right tool

- You need a unique image for a post, ad, slide, or story and don't want stock.
- You want a series of visually coherent images — pass `reference_image_b64`
  to anchor on a previous image's style.
- You're building a creative pipeline where the LLM should *decide what to draw*
  and call this tool to make it.

## What you get back

```json
{ "ok": true,
  "images": ["<base64-png>", "..."],
  "model": "gemini-3.1-flash-image-preview",
  "charged_usd": 0.0975 }
```

## Cost & billing

Each generated image costs ~$0.04 (Gemini's published rate) plus the platform
margin — roughly **$0.10 per image** charged to your Oya credits. If you set
your own `GEMINI_API_KEY` on the agent, billing is skipped and Google bills
you directly.

If your balance can't cover the call, the response is `{"ok": false,
"error": "insufficient_balance"}` — top up credits and retry.
