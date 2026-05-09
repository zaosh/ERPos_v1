"""
CV Service — Multi-model pipeline.

Phase A  (quick_analyze): GPT-4o-mini at intake. Fast, cheap. Fills type field.
Phase B  (deep_analyze):  GPT-4o on sold items. Rich analytics data.
Fashion  (analyze_fashion): FashionCLIP via HuggingFace for garment attributes.
Color    (detect_color):  K-means locally — no API cost, runs at capture time.

All API functions are called ONLY from queue_worker.py.
detect_color is called at POST /items/capture (synchronous, ~50ms).

=== EXCHANGE ITEM MARKER (TODO: activate once cards are printed) ===
When an exchanged item is photographed for re-entry into inventory, staff places a printed
card in the camera frame. Specification:

  Card size:     A6 (105mm x 148mm) or similar
  Card color:    Bright orange background
  Card text:     "EXCHANGE" in large black text (minimum 72pt font)
  Card position: Left of the garment, fully visible, not overlapping the garment
  Printing:      Print on cardstock, laminate for durability at the intake station

When detected: is_exchange_marker=True in cv_raw_output. The intake route flags the item
as is_exchange_item=True and skips Phase B and fashion jobs.

Current gate: EXCHANGE_MARKER_ENABLED = False
TODO: Flip to True ONLY after:
  1. Physical orange cards are printed and placed at the intake station
  2. A test image WITH the card confirms the prompt detects it correctly
  3. A test image WITHOUT the card confirms no false positives
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from PIL import Image

try:
    import numpy as np
    from sklearn.cluster import KMeans
    _KMEANS_AVAILABLE = True
except ImportError:
    np = None
    KMeans = None
    _KMEANS_AVAILABLE = False

from config import settings

logger = logging.getLogger(__name__)

# TODO: flip to True when orange exchange marker cards are printed and tested at intake station
EXCHANGE_MARKER_ENABLED = False

# ─── Named color map (K-means reference) ──────────────────────────────────────

NAMED_COLORS = {
    "black":  [0,   0,   0],
    "white":  [255, 255, 255],
    "grey":   [128, 128, 128],
    "red":    [220, 30,  30],
    "blue":   [30,  70,  200],
    "navy":   [0,   0,   128],
    "green":  [30,  150, 50],
    "yellow": [240, 200, 0],
    "orange": [240, 100, 0],
    "pink":   [240, 100, 150],
    "purple": [120, 30,  180],
    "brown":  [120, 70,  30],
    "beige":  [220, 190, 150],
}

# ─── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class PhaseAResult:
    type: str
    has_graphic: bool
    confidence: float
    needs_review: bool
    model_used: str
    processing_ms: int
    is_exchange_marker: bool = False


@dataclass
class PhaseBResult:
    label: Optional[str]
    graphic_description: Optional[str]
    style_era: Optional[str]
    visible_text: Optional[list[str]]
    condition_notes: Optional[str]
    resale_interest: str
    resale_reason: Optional[str]
    model_used: str
    processing_ms: int


@dataclass
class FashionResult:
    fit: Optional[str]
    sleeve: Optional[str]
    neckline: Optional[str]
    fabric_weight: Optional[str]
    style: Optional[str]
    decade_style: Optional[str]
    confidence_scores: dict = field(default_factory=dict)
    model_used: str = ""
    processing_ms: int = 0


# ─── Fashion attribute candidates ─────────────────────────────────────────────

_FASHION_CANDIDATES = {
    "fit":           ["oversized", "regular", "slim", "cropped"],
    "sleeve":        ["sleeveless", "short sleeve", "long sleeve", "three quarter"],
    "neckline":      ["crew neck", "v-neck", "collar", "hood", "turtleneck"],
    "fabric_weight": ["light", "medium", "heavy"],
    "style":         ["casual", "streetwear", "athletic", "formal", "vintage", "grunge", "preppy"],
    "decade_style":  ["1970s", "1980s", "1990s", "2000s", "2010s", "contemporary"],
}

# Map GPT type responses to ItemType enum values
_TYPE_MAP = {
    "plain":   "plain",
    "graphic": "graphic",
    "band":    "band",
    "anime":   "anime",
    "sports":  "sports",
    "branded": "branded",
    "vintage": "vintage_graphic",
    "holiday": "holiday",
    "pattern": "patterned",
    "unknown": "unknown",
}


# ─── Color detection (local K-means) ─────────────────────────────────────────

def _detect_color_sync(image_path: str) -> str:
    img = Image.open(image_path).convert("RGB")
    small = img.resize((100, 100))

    if _KMEANS_AVAILABLE:
        pixels = np.array(small).reshape(-1, 3).astype(float)
        non_white_mask = ~(np.all(pixels > 230, axis=1))
        if non_white_mask.sum() < 50:
            return "white"
        pixels = pixels[non_white_mask]
        k = min(3, len(pixels))
        kmeans = KMeans(n_clusters=k, n_init=3, random_state=42)
        kmeans.fit(pixels)
        counts = np.bincount(kmeans.labels_)
        dominant_rgb = kmeans.cluster_centers_[counts.argmax()]
        return _nearest_color(dominant_rgb)
    else:
        # Pillow quantize fallback when numpy/sklearn not available
        quantized = small.quantize(colors=3)
        palette = quantized.getpalette()
        histogram = quantized.histogram()
        best = max(range(3), key=lambda i: histogram[i])
        rgb = palette[best * 3: best * 3 + 3]
        if all(c > 230 for c in rgb):
            return "white"
        return _nearest_color(rgb)


def _nearest_color(rgb) -> str:
    min_dist = float("inf")
    best = "unknown"
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
    for name, ref in NAMED_COLORS.items():
        dist = ((r - ref[0]) ** 2 + (g - ref[1]) ** 2 + (b - ref[2]) ** 2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            best = name
    return best


async def detect_color(image_path: str) -> str:
    """Run K-means color detection in thread executor (CPU-bound)."""
    return await asyncio.to_thread(_detect_color_sync, image_path)


# ─── Image preparation helper ─────────────────────────────────────────────────

def _prepare_base64(image_path: str, target_size: int) -> str:
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((target_size, target_size), Image.LANCZOS)
    canvas = Image.new("RGB", (target_size, target_size), (255, 255, 255))
    offset = ((target_size - img.width) // 2, (target_size - img.height) // 2)
    canvas.paste(img, offset)
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ─── Phase A: quick_analyze ───────────────────────────────────────────────────

async def quick_analyze(image_path: str) -> PhaseAResult:
    """GPT-4o-mini type classification. Called by queue worker after item creation."""
    t0 = time.perf_counter()
    model = settings.CV_PHASE_A_MODEL

    _FALLBACK = PhaseAResult(
        type="unknown", has_graphic=False, confidence=0.0,
        needs_review=True, model_used="fallback",
        processing_ms=0,
    )

    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — cv_phase_a returning fallback")
        return _FALLBACK

    try:
        from openai import AsyncOpenAI
        b64 = await asyncio.to_thread(_prepare_base64, image_path, settings.CV_IMAGE_SIZE_PHASE_A)

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        exchange_marker_instruction = (
            'If you see a bright-orange A6 card with "EXCHANGE" in black text on the '
            'LEFT side of the frame, set "is_exchange_marker": true, '
            '"type": "unknown", "confidence": 1.0, "needs_review": false and stop. '
            "Otherwise set \"is_exchange_marker\": false and analyze the garment normally. "
        ) if EXCHANGE_MARKER_ENABLED else ""
        prompt = (
            "This is a thrift store garment on a white background. "
            + exchange_marker_instruction
            + "Reply in JSON only, no other text:\n"
            '{\n'
            '  "type": "one of [plain, graphic, band, anime, sports, branded, vintage, holiday, pattern, unknown]",\n'
            '  "has_graphic": true or false,\n'
            '  "confidence": 0.0 to 1.0,\n'
            '  "needs_review": true or false,\n'
            '  "is_exchange_marker": true or false\n'
            '}'
        )
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
                max_tokens=100,
            ),
            timeout=settings.CV_PROCESSING_TIMEOUT,
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        raw_type = str(data.get("type", "unknown")).lower()
        mapped_type = _TYPE_MAP.get(raw_type, "unknown")
        confidence = float(data.get("confidence", 0.5))

        return PhaseAResult(
            type=mapped_type,
            has_graphic=bool(data.get("has_graphic", False)),
            confidence=confidence,
            needs_review=bool(data.get("needs_review", confidence < settings.CV_CONFIDENCE_THRESHOLD)),
            model_used=model,
            processing_ms=int((time.perf_counter() - t0) * 1000),
            is_exchange_marker=bool(data.get("is_exchange_marker", False)) and EXCHANGE_MARKER_ENABLED,
        )

    except Exception as e:
        logger.error(f"quick_analyze failed: {e}")
        _FALLBACK.processing_ms = int((time.perf_counter() - t0) * 1000)
        return _FALLBACK


# ─── Phase B: deep_analyze ────────────────────────────────────────────────────

async def deep_analyze(image_path: str) -> PhaseBResult:
    """GPT-4o deep analysis for sold items. Called by queue worker nightly."""
    t0 = time.perf_counter()
    model = settings.CV_PHASE_B_MODEL

    _FALLBACK = PhaseBResult(
        label=None, graphic_description=None, style_era=None,
        visible_text=None, condition_notes=None,
        resale_interest="medium", resale_reason=None,
        model_used="fallback",
        processing_ms=0,
    )

    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — cv_phase_b returning fallback")
        return _FALLBACK

    try:
        from openai import AsyncOpenAI
        b64 = await asyncio.to_thread(_prepare_base64, image_path, settings.CV_IMAGE_SIZE_PHASE_B)

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        prompt = (
            "This is a thrift store garment. Analyze it for resale analytics. "
            "Reply in JSON only, no other text:\n"
            '{\n'
            '  "label": "brand/band/character name as string or null",\n'
            '  "graphic_description": "brief description or null",\n'
            '  "style_era": "decade as string (e.g. \'1990s\') or null",\n'
            '  "visible_text": ["array", "of", "strings"] or null,\n'
            '  "condition_notes": "visible wear or damage as string or null",\n'
            '  "resale_interest": "one of [low, medium, high, very_high]",\n'
            '  "resale_reason": "one brief sentence explaining why or null"\n'
            '}'
        )
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
                max_tokens=300,
            ),
            timeout=settings.CV_PROCESSING_TIMEOUT,
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        valid_interest = {"low", "medium", "high", "very_high"}
        resale_interest = str(data.get("resale_interest", "medium")).lower()
        if resale_interest not in valid_interest:
            resale_interest = "medium"

        return PhaseBResult(
            label=data.get("label"),
            graphic_description=data.get("graphic_description"),
            style_era=data.get("style_era"),
            visible_text=data.get("visible_text"),
            condition_notes=data.get("condition_notes"),
            resale_interest=resale_interest,
            resale_reason=data.get("resale_reason"),
            model_used=model,
            processing_ms=int((time.perf_counter() - t0) * 1000),
        )

    except Exception as e:
        logger.error(f"deep_analyze failed: {e}")
        _FALLBACK.processing_ms = int((time.perf_counter() - t0) * 1000)
        return _FALLBACK


# ─── FashionCLIP: analyze_fashion ────────────────────────────────────────────

async def analyze_fashion(image_path: str) -> FashionResult:
    """
    FashionCLIP zero-shot attribute extraction via HuggingFace Inference API.
    NEVER raises — on any failure returns null FashionResult.
    """
    t0 = time.perf_counter()

    _NULL = FashionResult(
        fit=None, sleeve=None, neckline=None, fabric_weight=None,
        style=None, decade_style=None, model_used="failed",
        processing_ms=0,
    )

    if not settings.HUGGINGFACE_API_KEY:
        logger.warning("HUGGINGFACE_API_KEY not set — fashion_attributes skipped")
        _NULL.model_used = "skipped"
        return _NULL

    try:
        b64 = await asyncio.to_thread(_prepare_base64, image_path, settings.CV_IMAGE_SIZE_PHASE_A)
        hf_url = f"https://api-inference.huggingface.co/models/{settings.CV_FASHION_MODEL}"
        headers = {"Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}"}

        results: dict[str, str] = {}
        confidence_scores: dict[str, dict] = {}

        async with httpx.AsyncClient(timeout=settings.CV_PROCESSING_TIMEOUT) as client:
            for attr, candidates in _FASHION_CANDIDATES.items():
                payload = {
                    "inputs": b64,
                    "parameters": {"candidate_labels": candidates},
                }
                resp = await client.post(hf_url, headers=headers, json=payload)

                if resp.status_code == 503:
                    # HF cold start — treat as retryable
                    raise RuntimeError(f"HuggingFace cold start (503): {resp.text[:200]}")

                if resp.status_code != 200:
                    logger.warning(f"HuggingFace {attr} returned {resp.status_code}: {resp.text[:200]}")
                    continue

                data = resp.json()
                if isinstance(data, list) and data:
                    top = max(data, key=lambda x: x.get("score", 0))
                    results[attr] = top["label"]
                    confidence_scores[attr] = {d["label"]: round(d["score"], 3) for d in data}

        return FashionResult(
            fit=results.get("fit"),
            sleeve=results.get("sleeve"),
            neckline=results.get("neckline"),
            fabric_weight=results.get("fabric_weight"),
            style=results.get("style"),
            decade_style=results.get("decade_style"),
            confidence_scores=confidence_scores,
            model_used=settings.CV_FASHION_MODEL,
            processing_ms=int((time.perf_counter() - t0) * 1000),
        )

    except Exception as e:
        logger.error(f"analyze_fashion failed (non-fatal): {e}")
        _NULL.processing_ms = int((time.perf_counter() - t0) * 1000)
        return _NULL
