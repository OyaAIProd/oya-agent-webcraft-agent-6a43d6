"""Generate images via Google's Gemini Flash Image (Nano Banana 2) — REST API.

Default model: `gemini-3.1-flash-image-preview` (Nano Banana 2). Supports both
text-to-image and image-to-image natively, plus `imageConfig.aspectRatio` for
9:16 / 16:9 / 4:5 / etc. — confirmed against the live Generative Language API
on 2026-05-03.

Falls back through `nano-banana-pro-preview` → `gemini-3-pro-image-preview` →
`gemini-2.5-flash-image` if the default 404s (Google renames previews
without warning), and finally to Imagen `imagen-4.0-generate-001` as a
last-resort text-to-image escape hatch (Imagen doesn't support image-to-image
on the GLM endpoint, so the fallback is skipped when reference_image_b64 is
provided).

Files are written to /tmp/oya_media/<uuid>.<ext> and the script emits
`A2ABASEAI_FILE: <path>` on stdout for each image — the platform parses
those, builds signed URLs at /api/sandbox/file/<token>, and caches to
Supabase Storage. The script's JSON payload is small (no inline base64).

Output (stdout):
    A2ABASEAI_FILE: /tmp/oya_media/img_<uuid>.jpg   (one per image)
    {"ok": true, "image_paths": [...], "num_images": 1, "model": "...",
     "aspect_ratio": "9:16", "charged_usd": 0.0975, "balance_usd": 9.90}

Reports usage via oya_runtime.report_usage (skipped when caller brought
their own GEMINI_API_KEY — see OYA_BILLING_BYO_KEYS).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import uuid

import httpx
import oya_runtime  # type: ignore[import-not-found]


# Nano Banana 2 + fallbacks. Default is the publicly-named preview; the
# explicit `nano-banana-pro-preview` alias is tried before the gemini-3-pro
# canonical name in case Google retires the friendly alias.
_GEMINI_DEFAULT = "gemini-3.1-flash-image-preview"
_GEMINI_FALLBACKS = (
    "nano-banana-pro-preview",
    "gemini-3-pro-image-preview",
    "gemini-2.5-flash-image",
)
# Imagen last-resort fallback for text-to-image only (different API shape, no
# image-to-image support on GLM). Iterated only when the entire Gemini chain
# fails AND no reference image was supplied.
_IMAGEN_FALLBACKS = (
    "imagen-4.0-generate-001",
    "imagen-4.0-fast-generate-001",
    "imagen-3.0-generate-002",
)
_VALID_ASPECTS = {"1:1", "9:16", "16:9", "4:5", "3:4", "4:3"}
_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_MEDIA_DIR = "/tmp/oya_media"

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _emit(payload: dict) -> None:
    print(json.dumps(payload))
    sys.exit(0 if payload.get("ok") else 1)


def _write_image(b64: str, mime_type: str = "image/png") -> str:
    os.makedirs(_MEDIA_DIR, exist_ok=True)
    ext = _MIME_TO_EXT.get(mime_type.lower(), "bin")
    path = f"{_MEDIA_DIR}/img_{uuid.uuid4().hex}.{ext}"
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    print(f"A2ABASEAI_FILE: {path}", flush=True)
    return path


def _gemini_call(
    api_key: str, model: str, prompt: str, ref_b64: str, aspect: str
) -> tuple[str | None, str | None, str | None, int | None]:
    """Gemini Flash Image :generateContent. Returns (path, mime_type, error, status).
    Supports both text-to-image and image-to-image. Aspect ratio passed via
    imageConfig (Nano Banana 2+; older models silently ignore the field)."""
    parts: list[dict] = []
    if ref_b64:
        parts.append({"inline_data": {"mime_type": "image/png", "data": ref_b64}})
    parts.append({"text": prompt})
    body: dict = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect},
        },
    }
    url = f"{_API_BASE}/models/{model}:generateContent?key={api_key}"
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(url, json=body, headers={"Content-Type": "application/json"})
    except httpx.HTTPError as exc:
        return None, None, f"http_error: {exc}", None
    if r.status_code >= 400:
        return None, None, r.text[:1000], r.status_code
    try:
        data = r.json()
    except Exception as exc:
        return None, None, f"json_decode: {exc}; body[:200]={r.text[:200]}", r.status_code
    for cand in (data.get("candidates") or []):
        for part in ((cand.get("content") or {}).get("parts") or []):
            inline = part.get("inline_data") or part.get("inlineData")
            if inline and inline.get("data"):
                mime_type = (inline.get("mime_type") or inline.get("mimeType") or "image/png")
                return _write_image(inline["data"], mime_type), mime_type, None, r.status_code
    return None, None, f"no_image_in_response: {json.dumps(data)[:500]}", r.status_code


def _imagen_call(
    api_key: str, model: str, prompt: str, aspect: str, num_images: int
) -> tuple[list[str], str | None, int | None]:
    """Imagen :predict — text-to-image fallback only (no image-to-image)."""
    url = f"{_API_BASE}/models/{model}:predict?key={api_key}"
    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": max(1, min(4, num_images)),
            "aspectRatio": aspect,
        },
    }
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(url, json=body, headers={"Content-Type": "application/json"})
    except httpx.HTTPError as exc:
        return [], f"http_error: {exc}", None
    if r.status_code >= 400:
        return [], r.text[:1000], r.status_code
    try:
        data = r.json()
    except Exception as exc:
        return [], f"json_decode: {exc}; body[:200]={r.text[:200]}", r.status_code
    paths: list[str] = []
    for pred in (data.get("predictions") or []):
        b64 = pred.get("bytesBase64Encoded") or pred.get("image", {}).get("bytesBase64Encoded")
        if b64:
            mime = pred.get("mimeType") or "image/png"
            paths.append(_write_image(b64, mime))
    if not paths:
        return [], f"no_predictions_in_response: {json.dumps(data)[:500]}", r.status_code
    return paths, None, r.status_code


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        _emit({"ok": False, "error": "GEMINI_API_KEY missing"})

    inp = json.loads(os.environ.get("INPUT_JSON") or "{}")
    prompt = (inp.get("prompt") or "").strip()
    if not prompt:
        _emit({"ok": False, "error": "prompt is required"})

    num_images = max(1, min(4, int(inp.get("num_images") or 1)))
    aspect = inp.get("aspect_ratio") or "1:1"
    if aspect not in _VALID_ASPECTS:
        aspect = "1:1"
    ref_b64 = inp.get("reference_image_b64") or ""

    image_paths: list[str] = []
    model_used = ""
    last_error: str | None = None
    last_status: int | None = None

    # Gemini chain (Nano Banana 2 → Pro → 3-pro → 2.5). One call per image.
    gemini_models = (_GEMINI_DEFAULT, *_GEMINI_FALLBACKS)
    for img_idx in range(num_images):
        path: str | None = None
        for model in gemini_models:
            path, mime, err, status = _gemini_call(api_key, model, prompt, ref_b64, aspect)
            if path:
                image_paths.append(path)
                model_used = model
                break
            last_error, last_status = err, status
            # Bail on auth/quota/policy errors; only walk fallbacks on
            # 404/503/'model not found' style errors.
            if status not in (404, 503) and not (
                status == 400 and err and ("model" in err.lower() or "not found" in err.lower())
            ):
                break
        if not path:
            break

    # Imagen last-resort fallback for text-to-image when the entire Gemini
    # chain failed (e.g. all Nano Banana variants 503 simultaneously) AND we
    # have no reference image (Imagen doesn't accept one).
    if not image_paths and not ref_b64:
        for model in _IMAGEN_FALLBACKS:
            paths, err, status = _imagen_call(api_key, model, prompt, aspect, num_images)
            if paths:
                image_paths = paths
                model_used = model
                break
            last_error, last_status = err, status
            if status not in (404, 503) and not (
                status == 400 and err and ("model" in err.lower() or "not found" in err.lower())
            ):
                break

    if not image_paths:
        _emit({
            "ok": False, "error": "image_generation_failed",
            "detail": last_error, "http_status": last_status,
            "models_tried": list(gemini_models) + (list(_IMAGEN_FALLBACKS) if not ref_b64 else []),
            "aspect_ratio": aspect,
            "had_reference_image": bool(ref_b64),
        })

    bill = oya_runtime.report_usage("gemini_image_gen", float(len(image_paths)), metadata={
        "model": model_used,
        "aspect_ratio": aspect,
    })
    if not bill.get("ok") and bill.get("status") == 402:
        _emit({"ok": False, "error": "insufficient_balance"})

    # Intentionally omit local sandbox paths from the JSON — the LLM has been
    # observed grabbing them and passing them as URLs to instagram_publish,
    # which then 400s. The signed URLs the orchestrator must use are appended
    # by the platform under "**Generated Files:**" via the A2ABASEAI_FILE
    # marker pattern; that's the ONLY place URLs come from.
    _emit({
        "ok": True,
        "num_images": len(image_paths),
        "model": model_used,
        "aspect_ratio": aspect,
        "charged_usd": float(bill.get("charged_usd") or 0),
        "balance_usd": float(bill.get("balance_usd") or 0),
        "url_source_note": "Read URLs from the 'Generated Files' block appended below by the platform (https://oya.ai/api/sandbox/file/<token>). Do not invent paths.",
    })


if __name__ == "__main__":
    main()
